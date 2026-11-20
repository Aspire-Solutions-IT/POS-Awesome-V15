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
def get_price_for_uom(item_code, price_list, uom, customer=None, delivery_charge=None):
    """Return Item Price for the given item, price list and UOM if it exists.

    A partner is priced exactly as their order is: the list comes from the customer and
    the order's delivery charge (never the ``price_list`` the browser sends), with the
    same date, currency, customer-row and fallback rules, and a UOM with no row of its
    own is the stock UOM price scaled by the conversion factor.
    """
    if not (item_code and uom):
        return None

    from posawesome.posawesome.api import partner_pricing

    if partner_pricing.is_partner_user():
        return partner_pricing.get_uom_rate(item_code, uom, customer, delivery_charge)

    if not price_list:
        return None

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
