"""Delivery-charge driven order type and price list (AP-1).

A Delivery Charge can name one Order Type and one Price List. Choosing it in the POS
makes the order that order type and prices it from that list:

* ``price_list_overrides_customer`` (container charges: FOB, DDP): only the charge's own
  price list is used.
* otherwise the customer's own price list is used, and any item missing from it falls back
  to the list's ``fallback_price_list`` (Stockist, or DHD for the DHD lists), then to the
  charge's price list.

Which charges and order types a POS may use comes from their ``Available To`` setting.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint

from customer_due_dates.selling.pos_availability import is_available

# The Order Type of a direct home delivery charge (seeded by customer_due_dates).
DHD_ORDER_TYPE = "DHD"


def _is_partner_mode() -> bool:
    from .partner_gate import is_partner_user

    return is_partner_user()


def get_charge(name):
    """The pricing facts of a delivery charge, or ``None`` when there is none to apply."""
    if not name or not frappe.db.exists("Delivery Charges", name):
        return None
    if not frappe.db.has_column("Delivery Charges", "order_type"):
        return None  # customer_due_dates has not been migrated yet

    row = frappe.db.get_value(
        "Delivery Charges",
        name,
        ["order_type", "price_list", "price_list_overrides_customer", "available_to"],
        as_dict=True,
    )
    row.name = name
    row.locked = bool(cint(row.price_list_overrides_customer) and row.price_list)
    return row


def assert_available(charge_name) -> None:
    """The charge must be one this POS is allowed to offer."""
    charge = get_charge(charge_name)
    if charge and not is_available(charge.available_to, _is_partner_mode()):
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )


def filter_available(charges: list) -> list:
    """Drop the charges this POS may not offer."""
    partner_mode = _is_partner_mode()
    return [c for c in charges if is_available(c.get("available_to"), partner_mode)]


def server_profile_context(user=None):
    """``(pos_profile, company)`` of the signed-in user, read from the database.

    Never from the request: a client-built profile JSON could name any company or profile
    and so make a charge look available. Same lookup as ``get_active_pos_profile``.
    """
    user = user or frappe.session.user
    profile = frappe.db.get_value("POS Profile User", {"user": user}, "parent")
    if not profile and frappe.get_meta("POS Settings").has_field("pos_profile"):
        profile = frappe.db.get_single_value("POS Settings", "pos_profile")
    company = frappe.db.get_value("POS Profile", profile, "company") if profile else None
    return profile or None, company or frappe.defaults.get_global_default("company")


def validated_partner_charge(charge_name, customer):
    """The charge a partner selected, once it is known to be offerable, else an error.

    Uses the same offer rules the POS charge dropdown applies
    (``get_applicable_delivery_charges``): enabled, this company, this POS profile, the
    customer's address charges, and available to partners. Run before any price is read.
    Returns ``None`` for no charge (or before the charge columns exist).
    """
    if not charge_name:
        return None

    charge = get_charge(charge_name)
    if charge is None:
        if frappe.db.exists("Delivery Charges", charge_name):
            return None  # customer_due_dates has not been migrated yet
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )

    assert_offered(charge_name, customer)
    return charge


def validated_charge_for_eta(charge_name, customer=None):
    """The charge for a display-only lookup (the fixed-ETA basket and grid), or an error.

    Partner and staff both get the POS offer rules (``assert_offered``) with the profile guard.
    Staff also need to be allowed to read the ``customer`` if one is given. Without a customer
    the address-charge restriction is not evaluated (it needs the customer's addresses).
    Returns ``None`` before the charge columns exist.
    """
    if not charge_name:
        return None
    if _is_partner_mode():
        charge = validated_partner_charge(charge_name, customer)
        if charge is not None:
            assert_profile_resolved(charge_name)
        return charge

    charge = get_charge(charge_name)
    if charge is None:
        if frappe.db.exists("Delivery Charges", charge_name):
            return None  # customer_due_dates has not been migrated yet
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )
    if frappe.db.get_value("Delivery Charges", charge_name, "disabled"):
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )
    if customer and not frappe.has_permission("Customer", "read", customer):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    assert_available(charge_name)
    assert_offered(charge_name, customer or None, require_profile=True)
    return charge


def assert_profile_resolved(charge_name) -> None:
    """A profile-restricted charge needs the user to have a resolved POS Profile.

    The offer rules accept a charge's profile row from *any* profile when no profile is
    given, so without this a user with no profile could use a charge restricted to others.
    """
    profile, _company = server_profile_context()
    if not profile and frappe.db.exists(
        "Delivery Charges POS Profile", {"parent": charge_name, "parenttype": "Delivery Charges"}
    ):
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )


def assert_offered(charge_name, customer=None, require_profile=False) -> None:
    """The charge must be in the POS charge dropdown for the server-side profile and company.

    Same rules as ``get_applicable_delivery_charges``: enabled, this company, this POS profile,
    available to this kind of user and, when a ``customer`` is given, restricted to the charges
    on that customer's addresses. With no ``customer`` the address restriction is not evaluated.
    ``require_profile`` also refuses a profile-restricted charge when the server resolves no POS
    profile (see ``assert_profile_resolved``).
    """
    from posawesome.posawesome.doctype.delivery_charges.delivery_charges import (
        get_applicable_delivery_charges,
    )

    if require_profile:
        assert_profile_resolved(charge_name)
    profile, company = server_profile_context()
    offered = get_applicable_delivery_charges(company, profile, customer) or []
    if charge_name not in {c.get("name") for c in offered}:
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )


def fallback_for(price_list, charge_name=None) -> str | None:
    """The list to price items from when they have no price on ``price_list``.

    Same currency only, so a fallback can never put a price in the wrong currency.
    """
    if not price_list:
        return None

    charge = get_charge(charge_name)
    if charge and charge.locked:
        return None

    candidates = []
    if frappe.db.has_column("Price List", "fallback_price_list"):
        candidates.append(frappe.db.get_value("Price List", price_list, "fallback_price_list"))
    if charge:
        candidates.append(charge.price_list)

    currency = frappe.db.get_value("Price List", price_list, "currency")
    for candidate in candidates:
        if (
            candidate
            and candidate != price_list
            and frappe.db.get_value("Price List", candidate, "currency") == currency
        ):
            return candidate
    return None


def apply_order_type(doc, method=None) -> None:
    """``Sales Order.before_validate``: a charge that names an order type sets it."""
    if getattr(doc, "_action", None) == "update_after_submit" or cint(doc.docstatus) == 2:
        return

    charge = get_charge(doc.get("posa_delivery_charges"))
    if not charge:
        return

    assert_available(charge.name)
    if charge.order_type and doc.meta.has_field("agiletfw_order_type"):
        doc.agiletfw_order_type = charge.order_type
