"""Next due-ins for the POS item selector tooltip (AP-15)."""

import frappe
from customer_due_dates.api.po_due_dates import get_next_due_ins

MAX_DUE_INS = 3


@frappe.whitelist()
def get_item_due_ins(item_code):
    """The next three purchase-order due dates for an item, with the quantity due on each.

    Quantities are net of Pre Allocation reservations, so they match the Due In QTY column.
    """
    frappe.has_permission("Item", ptype="read", throw=True)
    if not item_code or not frappe.db.exists("Item", item_code):
        return []
    return [
        {"due_date": str(row["due_date"]), "quantity_due_in": row["quantity_due_in"]}
        for row in get_next_due_ins(item_code, limit=MAX_DUE_INS)
    ]
