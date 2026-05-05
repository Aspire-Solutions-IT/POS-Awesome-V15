import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Sum
from frappe.utils import cint, cstr, flt, json
from erpnext.stock.doctype.batch.batch import get_batch_qty

STOCK_SOURCE_WAREHOUSE = "Agile Depot - AI"


def _kit_available_qty(item_code, warehouse):
    if not item_code or not warehouse:
        return None
    if not frappe.db.has_column("Item", "is_kit_item"):
        return None
    if not cint(frappe.db.get_value("Item", item_code, "is_kit_item") or 0):
        return None

    try:
        from customer_due_dates.item_due_dates.page.allocation_planner.allocation_planner import (
            fetch_item_warehouse_summary,
        )
    except Exception:
        return None

    try:
        rows = fetch_item_warehouse_summary(item_code) or []
    except Exception:
        return None

    for row in rows:
        if row.get("warehouse") == warehouse:
            return max(0.0, flt(row.get("available")))

    return 0.0


def _reserved_qty_by_item(warehouses, item_codes):
    if not warehouses or not item_codes:
        return {}

    rows = frappe.db.sql(
        """
        SELECT
            warehouse,
            item_code,
            SUM(GREATEST(0, reserved_qty - COALESCE(delivered_qty, 0))) AS reserved_qty
        FROM `tabStock Reservation Entry`
        WHERE docstatus = 1
          AND warehouse IN %(warehouses)s
          AND item_code IN %(item_codes)s
        GROUP BY warehouse, item_code
        """,
        {"warehouses": tuple(warehouses), "item_codes": tuple(item_codes)},
        as_dict=True,
    )
    return {(row.warehouse, row.item_code): flt(row.reserved_qty) for row in rows}

def get_stock_availability(item_code, warehouse):
    """Return total available quantity for an item in the given warehouse.

    ``warehouse`` can be either a single warehouse or a warehouse group.
    In case of a group, quantities from all child warehouses are summed up
    to provide an accurate availability figure.
    """

    warehouse = STOCK_SOURCE_WAREHOUSE
    if not warehouse:
        return 0.0

    kit_available = _kit_available_qty(item_code, warehouse)
    if kit_available is not None:
        return max(0.0, flt(kit_available))

    warehouses = [warehouse]
    if frappe.db.get_value("Warehouse", warehouse, "is_group"):
        # Include all child warehouses when a group warehouse is set
        warehouses = frappe.db.get_descendants("Warehouse", warehouse) or []

    bin_doctype = DocType("Bin")
    rows = (
        frappe.qb.from_(bin_doctype)
        .select(Sum(bin_doctype.actual_qty).as_("actual_qty"))
        .where(bin_doctype.item_code == item_code)
        .where(bin_doctype.warehouse.isin(warehouses))
        .run(as_dict=True)
    )
    on_hand = flt(rows[0].actual_qty) if rows else 0.0
    reserved_map = _reserved_qty_by_item(warehouses, [item_code])
    reserved_total = sum(flt(reserved_map.get((wh, item_code), 0.0)) for wh in warehouses)
    return max(0.0, on_hand - reserved_total)


@frappe.whitelist()
def get_bulk_stock_availability(items):
    """
    Fetch available stock for a list of items.

    Args:
        items: List of dicts/objects with 'item_code', 'warehouse', and optional 'batch_no'.

    Returns:
        dict: key=(item_code, warehouse, batch_no), value=qty
    """
    if not items:
        return {}

    # Separate items
    regular_items_map = {}  # (warehouse) -> set(item_code)
    results = {}

    for d in items:
        item_code = d.get("item_code")
        warehouse = STOCK_SOURCE_WAREHOUSE
        batch_no = cstr(d.get("batch_no"))  # Normalize to empty string

        if not item_code or not warehouse:
            continue

        if batch_no:
            # Fallback to existing single fetch for batches for now
            results[(item_code, warehouse, batch_no)] = flt(get_batch_qty(batch_no, warehouse))
        else:
            if warehouse not in regular_items_map:
                regular_items_map[warehouse] = set()
            regular_items_map[warehouse].add(item_code)

    if not regular_items_map:
        return results

    # Identify warehouse groups
    all_warehouses = list(regular_items_map.keys())
    group_warehouses = set(
        frappe.get_all("Warehouse", filters={"name": ["in", all_warehouses], "is_group": 1}, pluck="name")
    )

    bin_doctype = DocType("Bin")

    for warehouse, item_codes in regular_items_map.items():
        if not item_codes:
            continue

        target_warehouses = [warehouse]
        if warehouse in group_warehouses:
            target_warehouses = frappe.db.get_descendants("Warehouse", warehouse) or []

        if not target_warehouses:
            for code in item_codes:
                results[(code, warehouse, "")] = 0.0
            continue

        # Chunking item_codes if too many (SQL IN limit usually 1000s, invoices are smaller)
        item_code_list = list(item_codes)

        query = (
            frappe.qb.from_(bin_doctype)
            .select(bin_doctype.item_code, Sum(bin_doctype.actual_qty).as_("actual_qty"))
            .where(bin_doctype.item_code.isin(item_code_list))
            .where(bin_doctype.warehouse.isin(target_warehouses))
            .groupby(bin_doctype.item_code)
        )

        rows = query.run(as_dict=True)
        on_hand_map = {r.item_code: flt(r.actual_qty) for r in rows}
        reserved_map = _reserved_qty_by_item(target_warehouses, item_code_list)

        for code in item_codes:
            kit_available = _kit_available_qty(code, warehouse)
            if kit_available is not None:
                results[(code, warehouse, "")] = max(0.0, flt(kit_available))
                continue
            reserved_total = sum(flt(reserved_map.get((wh, code), 0.0)) for wh in target_warehouses)
            results[(code, warehouse, "")] = max(0.0, on_hand_map.get(code, 0.0) - reserved_total)

    return results


@frappe.whitelist()
def get_available_qty(items):
    """Return available stock quantity for given items.

    Args:
        items (str | list[dict]): JSON string or list of dicts with
            item_code, warehouse and optional batch_no.

    Returns:
        list: List of dicts with item_code, warehouse and available_qty
            in stock UOM.
    """

    if isinstance(items, str):
        items = json.loads(items)

    result = []
    for it in items or []:
        item_code = it.get("item_code")
        warehouse = STOCK_SOURCE_WAREHOUSE
        batch_no = it.get("batch_no")

        if not item_code or not warehouse:
            continue

        if batch_no:
            available_qty = get_batch_qty(batch_no, warehouse) or 0
        else:
            available_qty = get_stock_availability(item_code, warehouse)

        result.append(
            {
                "item_code": item_code,
                "warehouse": warehouse,
                "available_qty": flt(available_qty),
            }
        )

    return result
