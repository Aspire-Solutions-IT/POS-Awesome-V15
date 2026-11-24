"""Free-typed delivery address for a DHD order (AP-1).

A DHD (direct home delivery) order goes to an address typed at the POS. It is saved once as
a reusable Shipping Address on the customer: typing the same line 1 and postcode again
returns the address already there instead of a duplicate.

Two kinds of caller are accepted, both decided before any lookup:

* a scoped partner, for their own customers only. The Address is inserted with
  ``ignore_permissions`` because a partner has no Address write permission, so every check
  (charge, customer scope, profile, fields) runs first, and only a fixed set of fields is
  ever copied;
* desk/POS staff: a System User who holds Address create and Customer read permission. They
  insert with their normal permissions.

Anyone else (Guest, Website User that is not a scoped partner) is refused.

Every field is plain text: markup, entities, control characters and JSON-looking values are
rejected, because Frappe renders some Address fields unescaped. The Address name is opaque
(customer + random hash), never derived from the street text.
"""

import json
import re

import frappe
from frappe import _
from frappe.utils import cstr

from .charge_pricing import DHD_ORDER_TYPE

# Accepted key -> Address field. "postcode" is the UK spelling the POS form uses.
FIELD_MAP = {
    "address_line1": "address_line1",
    "address_line2": "address_line2",
    "city": "city",
    "county": "county",
    "pincode": "pincode",
    "postcode": "pincode",
    "country": "country",
    "phone": "phone",
    "email_id": "email_id",
    "email": "email_id",
}
REQUIRED = ("address_line1", "city", "pincode", "country")
MAX_LENGTH = {
    "address_line1": 140,
    "address_line2": 140,
    "city": 140,
    "county": 140,
    "pincode": 20,
    "country": 140,
    "phone": 30,
    "email_id": 140,
}


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_ENTITY = re.compile(r"&#?\w+;")


def normalise_line(value) -> str:
    """Casefolded, punctuation dropped, whitespace collapsed: '10, High  St.' == '10 high st'."""
    text = re.sub(r"[^\w\s]", " ", cstr(value).casefold())
    return " ".join(text.split())


def normalise_postcode(value) -> str:
    return re.sub(r"\s+", "", cstr(value)).upper()


def _assert_plain_text(key, text: str) -> None:
    """Reject anything that could be read back as markup or as a structured value."""
    bad = "<" in text or ">" in text or _ENTITY.search(text)
    if not bad and text[:1] in ("{", "["):
        try:
            bad = isinstance(json.loads(text), (dict, list))
        except ValueError:
            bad = False
    if bad:
        frappe.throw(
            _("Address field {0} must be plain text.").format(frappe.bold(key)),
            frappe.ValidationError,
        )


def _parse_address(address) -> dict:
    if isinstance(address, str):
        try:
            address = frappe.parse_json(address)
        except Exception:
            frappe.throw(_("The address is not valid."), frappe.ValidationError)
    if not isinstance(address, dict):
        frappe.throw(_("The address is not valid."), frappe.ValidationError)

    clean: dict[str, str] = {}
    for key, value in address.items():
        field = FIELD_MAP.get(key)
        if field is None:
            frappe.throw(
                _("Address field {0} is not allowed.").format(frappe.bold(key)),
                frappe.ValidationError,
            )
        if value is not None and not isinstance(value, (str, int, float)):
            frappe.throw(
                _("Address field {0} is not valid.").format(frappe.bold(key)),
                frappe.ValidationError,
            )
        text = " ".join(_CONTROL.sub("", cstr(value or "")).split())
        _assert_plain_text(key, text)
        if len(text) > MAX_LENGTH[field]:
            frappe.throw(
                _("Address field {0} is too long (at most {1} characters).").format(
                    frappe.bold(key), MAX_LENGTH[field]
                ),
                frappe.ValidationError,
            )
        if text:
            if clean.get(field) not in (None, text):
                frappe.throw(
                    _("Address field {0} is given twice.").format(frappe.bold(key)),
                    frappe.ValidationError,
                )
            clean[field] = text

    for field in REQUIRED:
        if not clean.get(field):
            frappe.throw(
                _("Address field {0} is required.").format(frappe.bold(field)),
                frappe.ValidationError,
            )

    if clean.get("email_id"):
        from .email_validation import validate_optional_email

        clean["email_id"] = validate_optional_email(clean["email_id"])

    return clean


def _validated_dhd_charge(delivery_charge, customer, partners):
    """The charge, once it is known to be offerable here and to be a DHD one, else an error."""
    from . import charge_pricing

    if not delivery_charge or not isinstance(delivery_charge, str):
        frappe.throw(_("Select the DHD delivery charge first."), frappe.ValidationError)

    if partners is not None:
        charge = charge_pricing.validated_partner_charge(delivery_charge, customer)
    else:
        charge = charge_pricing.get_charge(delivery_charge)
        if charge is None or frappe.db.get_value("Delivery Charges", delivery_charge, "disabled"):
            frappe.throw(
                _("Delivery charge {0} is not available here.").format(frappe.bold(delivery_charge)),
                frappe.PermissionError,
            )
        charge_pricing.assert_available(delivery_charge)

    if charge is None or charge.order_type != DHD_ORDER_TYPE:
        frappe.throw(
            _("A delivery address can only be added for a DHD delivery charge."), frappe.ValidationError
        )
    return charge


def _existing_address(customer, line1, postcode):
    """A live Shipping address linked to the customer with this line 1 and postcode.

    ``FOR UPDATE`` makes this a current read, so an address committed by a concurrent
    request is seen even inside this request's older snapshot.
    """
    rows = frappe.db.sql(
        """
        SELECT address.name, address.address_line1, address.pincode
        FROM `tabAddress` AS address
        INNER JOIN `tabDynamic Link` AS link ON address.name = link.parent
        WHERE link.parenttype = 'Address'
            AND link.link_doctype = 'Customer'
            AND link.link_name = %s
            AND address.address_type = 'Shipping'
            AND address.disabled = 0
        ORDER BY address.creation
        FOR UPDATE
        """,
        (customer,),
        as_dict=True,
    )
    wanted_line = normalise_line(line1)
    wanted_postcode = normalise_postcode(postcode)
    for row in rows:
        if (
            normalise_line(row.address_line1) == wanted_line
            and normalise_postcode(row.pincode) == wanted_postcode
        ):
            return row.name
    return None


def _assert_staff(customer) -> None:
    """Desk/POS staff only: a System User with Address create and Customer read access.

    Same check the other POS endpoints lean on (``frappe.has_permission``), plus the user
    type, so a Website User or Guest granted a role by mistake still cannot get in. Runs
    before any lookup, so nothing about existing addresses is revealed.
    """
    user = frappe.session.user
    if (
        not user
        or user == "Guest"
        or frappe.db.get_value("User", user, "user_type") != "System User"
        or not frappe.has_permission("Address", "create")
        or not frappe.has_permission("Customer", "read")
    ):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    if frappe.db.exists("Customer", customer) and not frappe.has_permission("Customer", "read", customer):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def _assert_partner_profile(charge_name) -> None:
    """A profile-restricted charge needs the partner to have a resolved POS Profile.

    The offer rules accept a charge's profile row from *any* profile when no profile is
    given, so without this a partner with no profile could use a charge restricted to others.
    """
    from . import charge_pricing

    profile, _company = charge_pricing.server_profile_context()
    if not profile and frappe.db.exists(
        "Delivery Charges POS Profile", {"parent": charge_name, "parenttype": "Delivery Charges"}
    ):
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )


def _address_title(customer: str) -> str:
    """Short opaque title (the Address name is title + type): customer id plus a random hash."""
    label = _CONTROL.sub("", cstr(customer)).replace("<", "").replace(">", "")[:80].strip()
    return f"{label}-{frappe.generate_hash(length=10)}"


@frappe.whitelist(methods=["POST"])
def create_order_address(customer, delivery_charge, address):
    """Save a typed DHD delivery address on the customer; returns ``{name, created}``.

    ``name`` is the Address to use as ``shipping_address_name``.
    """
    from .partner_gate import customer_scope_partners, is_customer_in_scope

    if not customer or not isinstance(customer, str):
        frappe.throw(_("Select a customer first."), frappe.ValidationError)

    partners = customer_scope_partners()
    if partners is not None:
        if not is_customer_in_scope(customer, partners):
            frappe.throw(_("Not permitted"), frappe.PermissionError)
    else:
        _assert_staff(customer)
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} was not found.").format(frappe.bold(customer)), frappe.DoesNotExistError)

    _validated_dhd_charge(delivery_charge, customer, partners)
    if partners is not None:
        _assert_partner_profile(delivery_charge)
    fields = _parse_address(address)
    if not frappe.db.exists("Country", fields["country"]):
        frappe.throw(
            _("Country {0} was not found.").format(frappe.bold(fields["country"])),
            frappe.ValidationError,
        )

    # Serialise per customer: a second concurrent request waits here, then sees the first's address.
    customer = frappe.db.get_value("Customer", customer, "name", for_update=True) or customer

    existing = _existing_address(customer, fields["address_line1"], fields["pincode"])
    if existing:
        return {"name": existing, "created": False}

    doc = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": _address_title(customer),
            "address_type": "Shipping",
            "links": [{"link_doctype": "Customer", "link_name": customer}],
            **fields,
        }
    )
    try:
        doc.insert(ignore_permissions=partners is not None)
    except frappe.DuplicateEntryError:
        existing = _existing_address(customer, fields["address_line1"], fields["pincode"])
        if existing:
            return {"name": existing, "created": False}
        raise
    return {"name": doc.name, "created": True}
