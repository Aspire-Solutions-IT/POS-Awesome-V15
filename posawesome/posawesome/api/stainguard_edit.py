"""Staingard rules for editing a submitted Sales Order from POS Sales Order Management.

Staingard's PUT replaces the whole warranty, and customer_due_dates (cdd) resyncs the
complete warranty whenever a submitted order is edited, so POS can edit an order that
holds a warranty as long as the edit goes through cdd's update path. The rules that keep
the warranty and the order in step:

1. Once the warranty has a delivery date (Staingard has approved it) nothing on the order,
   or on any other order of its split, can be edited: delivered_lock_reason.
2. The Staingard line is the warranty itself. It cannot be removed or have its item, qty
   or rate edited, and no cover can be added from POS: see validate_cover_rows and the item
   lock in sales_orders._build_managed_sales_order_item_lock.
3. When an edit moves the value of what is covered into another band the line is swapped
   for the item of the new band, at its price. plan_cover_swap works the swap out so the
   preview and the payment taken include it. cdd's Update Items path makes the swap itself
   when it has the warranty guard (customer_due_dates.staingard.order_guard) and the
   warranty is registered, and rejects a payload that already carries one; otherwise POS
   applies the swap to the rows it sends - on the order that holds the cover, which may be
   another order of the split (see sales_orders._apply_managed_sales_order_items). An edit that leaves no band
   covering the new value is refused.

cdd is optional here: its guard is used for rule 1 when it is installed, and the same rule
is mirrored from the order's own stored warranty payload when it is not, so POS never
hard-fails on a bench whose cdd predates the guard.

A stored warranty payload that cannot be parsed counts as locked, with its own message.
cdd's guard raises a bare JSON error on it (its _stored_payload is a plain parse), so POS
catches that, falls back to the same local rule and locks the order: POS and Desk agree
that the order is not editable, POS just says why.
"""

import json
from types import SimpleNamespace

import frappe
from frappe import _
from frappe.utils import cstr, flt


def _customer_services():
    return _("Please contact Customer Services.")


# --------------------------------------------------------------------------
# Which items are Staingard cover
# --------------------------------------------------------------------------


def cover_item_codes(item_codes) -> set:
    """The Staingard items among `item_codes`."""
    codes = list({code for code in item_codes if code})
    if not codes or not frappe.db.has_column("Item", "is_staingard_item"):
        return set()
    return set(frappe.get_all("Item", filters={"name": ["in", codes], "is_staingard_item": 1}, pluck="name"))


def order_cover_codes(doc) -> set:
    return cover_item_codes(getattr(row, "item_code", None) for row in getattr(doc, "items", []) or [])


# --------------------------------------------------------------------------
# Which warranty an order belongs to, and whether it has been delivered
# --------------------------------------------------------------------------


# What marks cdd's guard as one that swaps the cover itself: vet_update_items and
# follow_band are its Update Items entry points; prepare_update_items is what they were
# before they were split in two.
CDD_GUARD_ENTRY_POINTS = ("vet_update_items", "prepare_update_items")


def _cdd_order_guard():
    """cdd's Staingard order guard, or None when the installed cdd does not have it."""
    try:
        from customer_due_dates.staingard import order_guard
    except ImportError:
        return None
    return order_guard if any(hasattr(order_guard, name) for name in CDD_GUARD_ENTRY_POINTS) else None


def _find_offer(amount):
    """The Staingard Item that covers an order worth `amount`, None when none does (or
    when cdd's Staingard support is not installed, so nothing could be offered)."""
    try:
        from customer_due_dates.staingard.pos import find_offer
    except ImportError:
        return None
    return find_offer(amount)


def split_group(doc) -> list:
    """Every submitted order of the POS split `doc` belongs to, `doc` itself as it stands
    in memory included; just `[doc]` for an order that was not split."""
    batch = (
        getattr(doc, "split_order_batch", None)
        if frappe.db.has_column("Sales Order", "split_order_batch")
        else None
    )
    if not batch:
        return [doc]

    names = frappe.get_all(
        "Sales Order",
        filters={"split_order_batch": batch, "docstatus": 1},
        order_by="creation asc, name asc",
        pluck="name",
    )
    group = [doc if name == doc.name else frappe.get_doc("Sales Order", name) for name in names]
    return group or [doc]


def warranty_context(doc):
    """For a submitted order of a split that holds a registered warranty: `owner` (the
    order storing the warranty id), `group` (the submitted orders it covers) and `delivery`
    (why the warranty counts as delivered, None while it is not). None for any other order.

    cdd's own rule is used when its guard is installed, so POS and Desk agree; if that
    cannot be called the same rule is read from the order data here."""
    guard = _cdd_order_guard()
    if guard is not None and hasattr(guard, "_warranty_context"):
        try:
            context = guard._warranty_context(doc)
        except Exception:
            # Expected for a stored payload that is not JSON (cdd parses it without a
            # fallback): the local rule locks that order, so it is not worth an Error Log
            # row on every load. Anything else is.
            fallback = _mirrored_warranty_context(doc)
            if not (fallback and _payload_unreadable(fallback.owner)):
                frappe.log_error(title="POS Staingard warranty check (cdd) failed; using the local rule")
            return fallback
        if not context:
            return None
        return SimpleNamespace(owner=context["owner"], group=list(context["group"]), delivery=context["delivery"])
    return _mirrored_warranty_context(doc)


def _mirrored_warranty_context(doc):
    if getattr(doc, "docstatus", None) != 1 or not frappe.db.has_column(
        "Sales Order", "staingard_warranty_id"
    ):
        return None

    group = split_group(doc)
    owner = next((order for order in group if getattr(order, "staingard_warranty_id", None)), None)
    if not owner:
        return None
    return SimpleNamespace(owner=owner, group=group, delivery=_mirrored_delivery_state(owner, group))


def _stored_payload(owner):
    """The warranty payload last stored on `owner`: (payload dict or None, readable)."""
    raw = getattr(owner, "staingard_warranty_payload", None)
    if not raw:
        return None, True
    try:
        stored = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return None, False
    return (stored if isinstance(stored, dict) else None), True


def _payload_unreadable(owner) -> bool:
    return not _stored_payload(owner)[1]


def _mirrored_delivery_state(owner, group):
    """What says the warranty has been delivered, None while it has not (cdd's
    _delivery_state): the delivery date in the payload last stored on the owner; no stored
    payload at all, which only happened for warranties registered after delivery; or every
    item of the split delivered, the date being on its way. A stored payload that cannot be
    parsed locks the order too: nothing says the warranty has not been delivered."""
    stored, readable = _stored_payload(owner)
    if not readable:
        return _("its stored warranty record could not be read")
    if stored is None:
        return _("the warranty was registered after delivery")
    if stored.get("delivery_date"):
        return _("delivery date {0}").format(stored["delivery_date"])
    if _group_fully_delivered(group):
        return _("every item has been delivered")
    return None


def _group_fully_delivered(group) -> bool:
    """Every order of the split delivered in full, the warranty line itself not counting
    (it is never physically delivered)."""
    covers = cover_item_codes(row.item_code for order in group for row in order.items)
    deliverable = [
        [row for row in order.items if row.item_code not in covers]
        for order in group
        if any(row.item_code not in covers for row in order.items)
    ]
    return bool(deliverable) and all(
        all(flt(row.delivered_qty) >= flt(row.qty) for row in rows) for rows in deliverable
    )


def delivered_lock_reason(doc):
    """The message locking POS editing of `doc` because its Staingard warranty has a
    delivery date, or None when the order is not in that state."""
    context = warranty_context(doc)
    if not context or not context.delivery:
        return None
    reference = getattr(context.owner, "staingard_warranty_reference", None) or getattr(
        context.owner, "staingard_warranty_id", None
    )
    return _(
        "This order is covered by Stainguard warranty {0} ({1}), so it can no longer be edited in POS. {2}"
    ).format(reference, context.delivery, _customer_services())


# --------------------------------------------------------------------------
# The cover line
# --------------------------------------------------------------------------


def validate_cover_rows(doc, normalized_items):
    """Refuse an edit that adds a Staingard line: the cover is placed with the order and
    swapped by the band rules, never chosen by hand. Removing or editing the order's own
    cover line is refused by its item lock."""
    covers = order_cover_codes(doc)
    existing_cover = {row.name for row in doc.items if row.item_code in covers}
    incoming_cover = cover_item_codes(row.get("item_code") for row in normalized_items)
    for row in normalized_items:
        if row.get("item_code") in incoming_cover and row.get("docname") not in existing_cover:
            frappe.throw(
                _("Stainguard cover {0} is set automatically from the order's value and cannot be added in POS.").format(
                    row["item_code"]
                ),
                title=_("Stainguard cover"),
            )


def _covered_amount(group, edited_name=None, edited_items=None, covers=frozenset()) -> float:
    """The value the cover is banded on, as the POS and cdd compute it: every item of the
    split except the cover itself, less the orders' additional discount. `edited_items`
    stands in for the rows of the order being edited."""
    amount = 0.0
    for order in group:
        rows = edited_items if edited_items is not None and order.name == edited_name else order.items
        for row in rows:
            code = row.get("item_code") if isinstance(row, dict) else getattr(row, "item_code", None)
            if not code or code in covers:
                continue
            qty = row.get("qty") if isinstance(row, dict) else getattr(row, "qty", 0)
            rate = row.get("rate") if isinstance(row, dict) else getattr(row, "rate", 0)
            amount += flt(qty) * flt(rate)
        amount -= abs(flt(getattr(order, "discount_amount", 0)))
    return flt(amount, 2)


def _cover_price(owner, item_code) -> float:
    """The cover's premium: its price on the order's selling price list, in the order's
    currency (what cdd swaps the line to, and the POS sells it at, with no discount)."""
    from erpnext.stock.get_item_details import get_price_list_rate_for

    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
    rate = get_price_list_rate_for(
        frappe._dict(
            price_list=owner.selling_price_list,
            customer=owner.customer,
            qty=1,
            uom=stock_uom,
            stock_uom=stock_uom,
            conversion_factor=1,
            transaction_date=owner.transaction_date,
        ),
        item_code,
    )
    if not flt(rate):
        frappe.throw(
            _("Stainguard cover {0} has no price on price list {1}, so the order cannot move to it.").format(
                item_code, owner.selling_price_list
            ),
            title=_("No Stainguard cover price"),
        )

    price_list_currency = getattr(owner, "price_list_currency", None)
    currency = getattr(owner, "currency", None)
    if price_list_currency and currency and price_list_currency != currency:
        rate = flt(rate) * flt(getattr(owner, "plc_conversion_rate", None) or 1) / flt(
            getattr(owner, "conversion_rate", None) or 1
        )
    return flt(rate)


def _unchanged_row(row) -> dict:
    """An Update Items payload row that leaves a Sales Order row exactly as it is."""
    delivery_date = getattr(row, "delivery_date", None)
    return {
        "docname": row.name,
        "item_code": row.item_code,
        "warehouse": getattr(row, "warehouse", None),
        "delivery_date": str(delivery_date) if delivery_date else None,
        "uom": getattr(row, "uom", None),
        "description": getattr(row, "description", None),
        "bom_no": getattr(row, "bom_no", None),
        "qty": flt(row.qty),
        "rate": flt(row.rate),
        "conversion_factor": flt(getattr(row, "conversion_factor", 0) or 1),
    }


def plan_cover_swap(doc, normalized_items):
    """Work out whether the edit moves the order into another cover band.

    Returns `project_items` (the rows to price the change on: with the swap made when the
    cover line is on this order), `apply_items` (the rows to hand to the update: the same
    as the projection, except that cdd makes the swap itself when its guard is installed
    and the warranty is registered, and rejects a payload that already has it), and `swap`
    (None, or a description of the swap for the cashier). When the cover is on another order
    of the split `owner_items` holds the rows that order will have after the swap (to price
    it on) and `apply_on_owner` says whether POS has to make the swap there itself: it does
    unless cdd's guard does. Refuses the edit when no band covers the new value."""
    plan = SimpleNamespace(
        project_items=normalized_items,
        apply_items=normalized_items,
        swap=None,
        owner_items=None,
        apply_on_owner=False,
    )

    group = split_group(doc)
    covers = cover_item_codes(row.item_code for order in group for row in order.items)
    if not covers:
        return plan

    owner = next((order for order in group if any(row.item_code in covers for row in order.items)), None)
    if owner is None:
        return plan

    before = _covered_amount(group, covers=covers)
    after = _covered_amount(group, doc.name, normalized_items, covers)
    if before == after:
        return plan

    offer = _find_offer(after)
    if not offer:
        frappe.throw(
            _("After this change the order would be worth {0}, which no Stainguard cover covers, so it cannot be saved.").format(
                frappe.format_value(after, {"fieldtype": "Currency"})
            ),
            title=_("No Stainguard cover"),
        )

    line = next(row for row in owner.items if row.item_code in covers)
    if offer["item_code"] == line.item_code:
        return plan

    delegated = _cdd_order_guard() is not None and warranty_context(doc) is not None
    same_order = owner.name == doc.name

    premium = _cover_price(owner, offer["item_code"])
    plan.swap = {
        "from_item": line.item_code,
        "to_item": offer["item_code"],
        "to_item_name": offer.get("item_name") or offer["item_code"],
        "rate": premium,
        "covered_amount": after,
        "order": owner.name,
        "same_order": same_order,
        # What the old line is worth: the order's total moves by the difference.
        "old_rate": flt(getattr(line, "rate", 0)),
    }

    stock_uom, description = (
        frappe.db.get_value("Item", offer["item_code"], ["stock_uom", "description"]) or (None, None)
    )
    delivery_date = getattr(line, "delivery_date", None)
    new_row = {
        "docname": None,
        "item_code": offer["item_code"],
        "uom": stock_uom,
        "description": cstr(description) or offer.get("item_name") or offer["item_code"],
        "bom_no": None,
        "warehouse": cstr(getattr(line, "warehouse", "") or "").strip() or None,
        "qty": 1,
        "conversion_factor": 1,
        "rate": premium,
        "delivery_date": str(delivery_date) if delivery_date else None,
    }

    if not same_order:
        # The cover sits on another order of the split, so this order's own rows and total do
        # not change: the other order's do. cdd swaps the line there when its guard is
        # installed; otherwise POS does, the way cdd would (old cover row out, the new one in
        # at its price) - see sales_orders._apply_managed_sales_order_items.
        plan.owner_items = [_unchanged_row(row) for row in owner.items if row.name != line.name] + [new_row]
        plan.apply_on_owner = not delegated
        return plan

    plan.project_items = [row for row in normalized_items if row.get("docname") != line.name] + [new_row]
    plan.apply_items = normalized_items if delegated else plan.project_items
    return plan


def verify_swap(swap):
    """After the update: the order holding the cover must now hold exactly the cover the
    cashier was told about, at the premium quoted. Raises, rolling the whole edit (and any
    payment taken with it) back, when it does not - the premium charged would otherwise be
    for a cover the order does not hold, or at another price."""
    if not swap:
        return
    rows = frappe.get_all(
        "Sales Order Item", filters={"parent": swap["order"]}, fields=["item_code", "qty", "rate"]
    )
    held = [row for row in rows if row.get("item_code") == swap["to_item"]]
    if not held or (swap["from_item"] != swap["to_item"] and any(
        row.get("item_code") == swap["from_item"] for row in rows
    )):
        frappe.throw(
            _("The Stainguard cover could not be changed to {0}, so the change was not saved. {1}").format(
                swap["to_item"], _customer_services()
            ),
            title=_("Stainguard cover"),
        )

    saved = held[0]
    if len(held) != 1 or abs(flt(saved.get("rate")) - flt(swap["rate"])) > 0.005 or flt(saved.get("qty")) != 1:
        frappe.throw(
            _(
                "The Stainguard cover {0} was saved at {1} instead of the {2} quoted, so the change was not saved. {3}"
            ).format(
                swap["to_item"],
                flt(saved.get("rate")),
                flt(swap["rate"]),
                _customer_services(),
            ),
            title=_("Stainguard cover"),
        )
