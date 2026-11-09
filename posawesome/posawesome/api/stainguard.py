import frappe
from frappe import _
from frappe.utils import cint, flt


def validate_pos_stainguard(payload):
    enabled = cint(payload.pop("posa_stainguard_enabled", 0))
    if not frappe.db.has_column("Item", "is_staingard_item"):
        return

    lines = payload.get("items") or []
    codes = list({line.get("item_code") for line in lines if line.get("item_code")})
    cover_codes = set()
    if codes:
        cover_codes = set(
            frappe.get_all("Item", filters={"name": ["in", codes], "is_staingard_item": 1}, pluck="name")
        )
    cover = [line for line in lines if line.get("item_code") in cover_codes]
    if not enabled and not cover:
        return

    def reject():
        frappe.throw(_(
            "Stainguard cover is controlled by the Add stainguard checkbox. Please refresh the basket cover."
        ))

    if not enabled:
        reject()

    profile = frappe.get_cached_doc("POS Profile", payload.get("pos_profile"))
    profile.check_permission("read")
    if not cint(profile.get("posa_enable_stainguard")):
        reject()

    from customer_due_dates.staingard.pos import find_offer
    from posawesome.posawesome.api.item_processing.search import search_items_by_code

    amount = sum(
        flt(line.get("qty")) * flt(line.get("rate"))
        for line in lines if line.get("item_code") not in cover_codes
    ) - abs(flt(payload.get("discount_amount")))
    offer = find_offer(amount)
    priced = search_items_by_code(
        profile.name,
        price_list=payload.get("selling_price_list"),
        customer=payload.get("customer"),
        search_value=offer["item_code"],
        exact=1,
        limit=1,
    ) if offer else []
    if not priced:
        if cover:
            reject()
        return

    expected = priced[0]
    if len(cover) != 1 or cover[0].get("item_code") != offer["item_code"]:
        reject()
    row = cover[0]
    expected_rate = flt(expected.get("rate"))
    if expected.get("currency") and payload.get("currency") and expected["currency"] != payload["currency"]:
        from erpnext.setup.utils import get_exchange_rate

        expected_rate *= get_exchange_rate(
            expected["currency"], payload["currency"], payload.get("transaction_date")
        )
    if (
        flt(row.get("qty")) != 1
        or flt(row.get("rate"), 2) != flt(expected_rate, 2)
        or flt(row.get("discount_percentage"))
        or flt(row.get("discount_amount"))
        or cint(row.get("name_overridden"))
        or (row.get("item_name") and row["item_name"] != expected.get("item_name"))
        or (row.get("uom") and row["uom"] != expected.get("stock_uom"))
    ):
        reject()
