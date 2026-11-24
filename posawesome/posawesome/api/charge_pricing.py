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

    from posawesome.posawesome.doctype.delivery_charges.delivery_charges import (
        get_applicable_delivery_charges,
    )

    profile, company = server_profile_context()
    offered = get_applicable_delivery_charges(company, profile, customer) or []
    if charge_name not in {c.get("name") for c in offered}:
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(charge_name)),
            frappe.PermissionError,
        )
    return charge


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
