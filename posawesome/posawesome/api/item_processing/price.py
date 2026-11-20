import frappe
from frappe import _
from frappe.utils import flt
from posawesome.posawesome.api.item_processing.barcode import _parse_scale_barcode_data

@frappe.whitelist()
def update_price_list_rate(item_code, price_list, rate, uom=None):
    """Create or update Item Price for the given item and price list."""
    if not item_code or not price_list:
        frappe.throw(_("Item Code and Price List are required"))

    rate = flt(rate)
    filters = {"item_code": item_code, "price_list": price_list}
    if uom:
        filters["uom"] = uom
    else:
        filters["uom"] = ["in", ["", None]]

    name = frappe.db.exists("Item Price", filters)
    if name:
        doc = frappe.get_doc("Item Price", name)
        doc.price_list_rate = rate
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc(
            {
                "doctype": "Item Price",
                "item_code": item_code,
                "price_list": price_list,
                "uom": uom,
                "price_list_rate": rate,
                "selling": 1,
            }
        )
        doc.insert(ignore_permissions=True)

    frappe.db.commit()
    return _("Item Price has been added or updated")


@frappe.whitelist()
def get_price_for_uom(item_code, price_list, uom):
    """Return Item Price for the given item, price list and UOM if it exists."""
    if not (item_code and price_list and uom):
        return None

    from posawesome.posawesome.api import partner_pricing

    if partner_pricing.is_partner_user():
        # The gate has already limited price_list to lists the partner can price from.
        # Defence in depth: refuse here too, and never return another customer's row.
        from posawesome.posawesome.api.partner_gate import allowed_price_lists, get_scope

        if price_list not in allowed_price_lists(get_scope()["partners"]):
            frappe.throw(_("You are not permitted to do this."), frappe.PermissionError)
        return partner_pricing.get_visible_item_price(item_code, price_list, uom=uom)

    price = frappe.db.get_value(
        "Item Price",
        {
            "item_code": item_code,
            "price_list": price_list,
            "uom": uom,
        },
        "price_list_rate",
    )
    return price
