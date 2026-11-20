"""Which price lists a Sales Partner is priced from, decided in one place (AP-1).

The request gate (``partner_gate.allowed_price_lists``), the item grid, item details,
order pricing, single-price lookups and offline deltas all need the same answer: for this
customer and this delivery charge, which list is the rate read from, and which list
backs it up when the item has no price there. They used to work it out separately, and
could disagree. They now all call :func:`resolve_lists`.

Only ``frappe`` is imported here, so the rules can be tested without a site.
"""

from __future__ import annotations

import frappe
from frappe.utils import cint

# Item Price rows a partner may be priced from. ERPNext copies the selling and buying
# flags of a dual-purpose Price List onto its Item Price rows and keeps the supplier on
# them, so "selling = 1" alone can match a supplier's negotiated buying rate. A partner
# only ever sees a selling row that belongs to no supplier. A row with no customer is a
# generic price; a row with a customer is only used for that customer (see
# ``_fetch_item_prices``).
PARTNER_ROW_SQL = "selling = 1 AND IFNULL(supplier, '') = ''"


def selling_list_info(name):
    """``{currency, fallback_price_list}`` of an enabled selling Price List, else ``None``."""
    if not name:
        return None

    fields = ["enabled", "selling", "currency"]
    has_fallback = frappe.db.has_column("Price List", "fallback_price_list")
    if has_fallback:
        fields.append("fallback_price_list")

    row = frappe.db.get_value("Price List", name, fields, as_dict=True)
    if not row or not (cint(row.get("enabled")) and cint(row.get("selling"))):
        return None

    return frappe._dict(
        currency=row.get("currency"),
        fallback_price_list=row.get("fallback_price_list") if has_fallback else None,
    )


def is_locked(charge) -> bool:
    """A container charge (FOB, DDP): only its own price list is used."""
    return bool(charge and cint(charge.get("price_list_overrides_customer")) and charge.get("price_list"))


def resolve_lists(base_list, charge=None):
    """``(primary, fallback)`` for a customer's own list and an optional delivery charge.

    * A locked charge uses its own list and never falls back.
    * Otherwise the primary is the customer's list (their group's when they have none),
      then the charge's list.
    * Both lists must be enabled selling lists. The fallback is the primary list's own
      ``fallback_price_list``, then the charge's list, and must be in the primary's
      currency. A buying-only or disabled list is skipped, never used.

    Returns ``(None, None)`` when there is no usable primary list.
    """
    charge_list = (charge or {}).get("price_list")
    locked = is_locked(charge)
    primary = charge_list if locked else (base_list or charge_list)

    info = selling_list_info(primary)
    if not info:
        return None, None
    if locked:
        return primary, None

    for candidate in (info.fallback_price_list, charge_list):
        if not candidate or candidate == primary:
            continue
        candidate_info = selling_list_info(candidate)
        if candidate_info and candidate_info.currency == info.currency:
            return primary, candidate

    return primary, None
