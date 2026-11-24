"""Read-only fixed lead-time ETA for a basket that is not saved yet (AP-9, POS display).

``get_fixed_eta`` answers "what would this basket's ETAs be on this delivery charge?" for
charges whose Order Type has Fixed Lead-Time ETA (12 weeks express, 16 otherwise). It only
reads: nothing is saved and the order's own dates are untouched. The dates come from
``customer_due_dates.selling.fixed_eta.eta_for_lines``, the same code the saved order and the
quoted-delivery preview use, so the grid, basket and order agree.

The charge is resolved as ``create_order_address`` does: a partner goes through
``charge_pricing.validated_partner_charge`` (offered to this customer, partner-available),
staff through the plain charge plus the availability check. ``Delivery Charges.order_type`` is
an Order Type document id, which is what ``uses_fixed_eta`` expects.
"""

from __future__ import annotations

import math

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

MAX_ITEMS = 200
MAX_TEXT = 140


def _none_applies() -> dict:
    return {"applies": False, "lines": {}, "overall_eta": None, "weeks": {}}


def _bad(message):
    frappe.throw(message, frappe.ValidationError)


def _text(value, label, required=False):
    if value is None or value == "":
        if required:
            _bad(_("{0} is required.").format(label))
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        _bad(_("{0} is not valid.").format(label))
    value = str(value)
    if len(value) > MAX_TEXT:
        _bad(_("{0} is too long.").format(label))
    return value


def clean_items(items) -> list[dict]:
    """Validated basket rows ``{item_code, qty, key?, kit_group_id?}``; anything else is an error."""
    if isinstance(items, str):
        try:
            items = frappe.parse_json(items)
        except Exception:
            _bad(_("Items must be a list."))
    if items is None:
        return []
    if not isinstance(items, (list, tuple)):
        _bad(_("Items must be a list."))
    if len(items) > MAX_ITEMS:
        _bad(_("Too many items (at most {0}).").format(MAX_ITEMS))

    rows = []
    for item in items:
        if not isinstance(item, dict):
            _bad(_("Each item must be an object."))
        qty = item.get("qty", 1)
        if isinstance(qty, bool) or not isinstance(qty, (int, float, str)):
            _bad(_("Item quantity must be a number."))
        try:
            qty = float(qty)
        except ValueError:
            _bad(_("Item quantity must be a number."))
        if not math.isfinite(qty):
            _bad(_("Item quantity must be a number."))
        row = {"item_code": _text(item.get("item_code"), _("Item code"), required=True), "qty": flt(qty)}
        key = _text(item.get("key"), _("Item key"))
        if key is not None:
            row["key"] = key
        kit_group = _text(item.get("kit_group_id"), _("Kit group"))
        if kit_group is not None:
            row["kit_group_id"] = kit_group
        rows.append(row)
    return rows


def _resolve_charge(delivery_charge, customer):
    """The usable charge for this caller, or an error. Mirrors ``order_address``."""
    from . import charge_pricing
    from .partner_gate import customer_scope_partners, is_customer_in_scope

    partners = customer_scope_partners()
    if partners is not None:
        if customer and not is_customer_in_scope(customer, partners):
            frappe.throw(_("Not permitted"), frappe.PermissionError)
        return charge_pricing.validated_partner_charge(delivery_charge, customer or None)

    charge = charge_pricing.get_charge(delivery_charge)
    if charge is None:
        if frappe.db.exists("Delivery Charges", delivery_charge):
            return None  # customer_due_dates has not been migrated yet
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(delivery_charge)),
            frappe.PermissionError,
        )
    if frappe.db.get_value("Delivery Charges", delivery_charge, "disabled"):
        frappe.throw(
            _("Delivery charge {0} is not available here.").format(frappe.bold(delivery_charge)),
            frappe.PermissionError,
        )
    charge_pricing.assert_available(delivery_charge)
    return charge


@frappe.whitelist()
def get_fixed_eta(customer=None, delivery_charge=None, items=None, transaction_date=None):
    """``{applies, lines, overall_eta, weeks}`` for the basket on this charge. Read only.

    ``applies`` is False (and the rest empty) when there is no charge or its order type has no
    Fixed Lead-Time ETA. ``items`` is a list (or its JSON) of ``{item_code, qty, key?,
    kit_group_id?}``; ``lines`` and ``weeks`` are keyed by ``key`` (the row's position from 1
    if none). ``transaction_date`` defaults to today.
    """
    if customer is not None and not isinstance(customer, str):
        _bad(_("Customer is not valid."))
    if delivery_charge is not None and not isinstance(delivery_charge, str):
        _bad(_("Delivery charge is not valid."))
    rows = clean_items(items)
    try:
        date = getdate(transaction_date or nowdate())
    except Exception:
        _bad(_("Transaction date is not valid."))

    if not delivery_charge:
        return _none_applies()
    charge = _resolve_charge(delivery_charge, customer)
    if charge is None or not charge.order_type:
        return _none_applies()

    from customer_due_dates.selling.fixed_eta import eta_for_lines

    return eta_for_lines(charge.order_type, date, rows)
