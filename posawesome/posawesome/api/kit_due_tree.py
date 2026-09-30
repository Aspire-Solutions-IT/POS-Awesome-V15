"""Component due-date tree for kit / kit set items in the POS item selector."""

import frappe
from customer_due_dates.kit_items.server.kit_tree import build_kit_tree, roll_up_due

from posawesome.posawesome.api.item_processing.stock import (
    STOCK_SOURCE_WAREHOUSE,
    get_stock_availability,
)


def _add_available_qty(node, cache):
    code = node["item_code"]
    if code not in cache:
        cache[code] = get_stock_availability(code, STOCK_SOURCE_WAREHOUSE)
    node["available_qty"] = cache[code]
    for child in node["children"]:
        _add_available_qty(child, cache)


@frappe.whitelist()
def get_kit_due_tree(item_code):
    frappe.has_permission("Item", ptype="read", throw=True)

    tree = build_kit_tree(item_code)
    if not tree:
        frappe.throw(frappe._("Item {0} not found").format(item_code), frappe.DoesNotExistError)

    _add_available_qty(tree, {})
    roll_up_due(tree)
    return tree
