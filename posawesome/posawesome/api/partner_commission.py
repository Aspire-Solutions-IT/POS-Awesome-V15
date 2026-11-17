"""Commission owed to a sales partner, for the partner-only POS page (AP-20).

Reads the commission already stored on each submitted Sales Order, so the page follows
whatever rule the order was saved with (AP-13 changes that calculation, not this page).
Everything is scoped to the signed-in partner's own orders here on the server; the POS
allow-list is a second layer, not the only one.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

from posawesome.posawesome.api.partner_gate import get_scope

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _partner_scope():
    scope = get_scope()
    if not scope["is_partner"]:
        frappe.throw(_("Commission is only available to sales partners."), frappe.PermissionError)
    return scope["partners"]


@frappe.whitelist()
def get_partner_commission(delivered_only=0, from_date=None, to_date=None, limit=DEFAULT_PAGE_SIZE, offset=0):
    """The signed-in partner's commission on submitted Sales Orders.

    ``delivered_only`` keeps only orders that are fully delivered (``per_delivered`` is 100);
    part-delivered orders show only when it is off. The totals cover the whole filtered set,
    not just the page returned. Commission is stored in company currency, so rows and totals
    are in that one currency.
    """
    partners = _partner_scope()
    if not partners:
        return _empty()

    limit = max(1, min(cint(limit) or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE))
    offset = max(0, cint(offset))

    conditions = ["so.docstatus = 1", "so.sales_partner in %(partners)s"]
    values = {"partners": tuple(partners)}
    if cint(delivered_only):
        conditions.append("so.per_delivered >= 100")
    if from_date:
        conditions.append("so.transaction_date >= %(from_date)s")
        values["from_date"] = getdate(from_date)
    if to_date:
        conditions.append("so.transaction_date <= %(to_date)s")
        values["to_date"] = getdate(to_date)
    where = " and ".join(conditions)

    totals = frappe.db.sql(
        f"""
        select count(*) as orders,
               coalesce(sum(so.amount_eligible_for_commission), 0) as net_value,
               coalesce(sum(so.total_commission), 0) as commission
        from `tabSales Order` so
        where {where}
        """,
        values,
        as_dict=True,
    )[0]

    rows = frappe.db.sql(
        f"""
        select so.name, so.transaction_date, so.customer, so.customer_name, so.status,
               so.per_delivered,
               so.amount_eligible_for_commission as net_value,
               so.commission_rate, so.total_commission as commission
        from `tabSales Order` so
        where {where}
        order by so.transaction_date desc, so.creation desc
        limit %(limit)s offset %(offset)s
        """,
        {**values, "limit": limit, "offset": offset},
        as_dict=True,
    )
    for row in rows:
        row["delivered"] = 1 if flt(row["per_delivered"]) >= 100 else 0

    return {
        "rows": rows,
        "totals": {
            "orders": cint(totals["orders"]),
            "net_value": flt(totals["net_value"]),
            "commission": flt(totals["commission"]),
        },
        "currency": _company_currency(),
        "limit": limit,
        "offset": offset,
    }


def _company_currency():
    company = frappe.defaults.get_global_default("company")
    return frappe.get_cached_value("Company", company, "default_currency") if company else None


def _empty():
    return {
        "rows": [],
        "totals": {"orders": 0, "net_value": 0, "commission": 0},
        "currency": None,
        "limit": DEFAULT_PAGE_SIZE,
        "offset": 0,
    }
