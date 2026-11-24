"""Read-only fixed lead-time ETA for a basket that is not saved yet (AP-9, POS display).

``get_fixed_eta`` answers "what would this basket's ETAs be on this delivery charge?" for
charges whose Order Type has Fixed Lead-Time ETA (12 weeks express, 16 otherwise). It only
reads: nothing is saved and the order's own dates are untouched. The dates come from
``customer_due_dates.selling.fixed_eta.eta_for_lines``, the same code the saved order and the
quoted-delivery preview use, so the grid, basket and order agree.

The charge is validated by ``charge_pricing.validated_charge_for_eta`` for both kinds of user: the
POS offer rules (enabled, company, POS profile, Available To, and the customer's address charges when
a customer is given; not evaluated without one) plus the no-profile guard ``create_order_address`` uses. ``Delivery Charges.order_type`` is
an Order Type document id, which is what ``uses_fixed_eta`` expects.
"""

from __future__ import annotations

import datetime
import math

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

MAX_ITEMS = 200
MAX_TEXT = 140
MIN_DATE = datetime.date(2000, 1, 1)
MAX_DATE = datetime.date(2100, 1, 1)


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
    _reject_duplicate_keys(rows)
    return rows


def _reject_duplicate_keys(rows) -> None:
    """Keys are compared as text (as on the wire); an unkeyed row's key is ``#<position>``."""
    seen = set()
    for position, row in enumerate(rows, start=1):
        key = row.get("key", f"#{position}")
        if key in seen:
            _bad(_("Item key {0} is used more than once.").format(key))
        seen.add(key)


def _resolve_charge(delivery_charge, customer):
    """The usable charge for this caller, or an error.

    Partners must also have the customer in their scope. Both kinds then get the POS offer rules
    (``charge_pricing.validated_charge_for_eta``): enabled, company, POS profile, Available To and,
    when a customer is given, the customer's address charges.
    """
    from . import charge_pricing
    from .partner_gate import customer_scope_partners, is_customer_in_scope

    partners = customer_scope_partners()
    if partners is not None and customer and not is_customer_in_scope(customer, partners):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    return charge_pricing.validated_charge_for_eta(delivery_charge, customer or None)


_warned: set = set()


def _warn_once(key: str, message: str) -> None:
    if key in _warned:
        return
    _warned.add(key)
    try:
        frappe.log_error(title="Fixed ETA unavailable", message=message)
    except Exception:
        pass


@frappe.whitelist()
def get_fixed_eta(customer=None, delivery_charge=None, items=None, transaction_date=None):
    """``{applies, lines, overall_eta, weeks}`` for the basket on this charge. Read only.

    ``applies`` is False (and the rest empty) when there is no charge or its order type has no
    Fixed Lead-Time ETA. ``items`` is a list (or its JSON) of ``{item_code, qty, key?,
    kit_group_id?}``; ``lines`` and ``weeks`` are keyed by ``key`` as text (a row with no key is keyed
    ``#<position>``; duplicate keys are refused). ``transaction_date`` defaults to today (2000-01-01
    to 2100-01-01 only).
    """
    if customer is not None and not isinstance(customer, str):
        _bad(_("Customer is not valid."))
    if delivery_charge is not None and not isinstance(delivery_charge, str):
        _bad(_("Delivery charge is not valid."))
    rows = clean_items(items)
    try:
        date = getdate(transaction_date or nowdate())
    except Exception:
        date = None
    if date is None or not (MIN_DATE <= date <= MAX_DATE):
        _bad(_("Transaction date is not valid."))

    if not delivery_charge:
        return _none_applies()
    charge = _resolve_charge(delivery_charge, customer)
    if charge is None or not charge.order_type:
        return _none_applies()

    try:
        from customer_due_dates.selling.fixed_eta import eta_for_lines
    except ImportError:  # customer_due_dates is older than the basket ETA
        _warn_once("eta_for_lines", "customer_due_dates has no eta_for_lines; the basket ETA is off.")
        return _none_applies()

    return eta_for_lines(charge.order_type, date, rows)
