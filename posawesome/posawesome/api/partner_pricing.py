"""Locked pricing for the Sales Partner POS (AP-1).

For a partner user, price comes from exactly one place: the Item Price on the
customer's own ``default_price_list``. The item's TFW price and on-sale price, which
the normal POS puts ahead of the price list, are ignored; discounts, margins and
pricing rules are switched off; and a line with no price on that list cannot be
added. Item cost fields are never sent to the browser.

Everything here is a no-op for anyone who is not a partner user.
"""

from __future__ import annotations

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from .partner_gate import PARTNER_MAX_DISCOUNT, get_scope, is_customer_in_scope, is_partner_user

# Rounding slack when comparing a percentage that came from currency amounts.
DISCOUNT_TOLERANCE = 0.01

# Cost and retail-override fields that exist on the POS item rows and ERPNext's item
# details but must not reach a partner's browser.
HIDDEN_ITEM_FIELDS = (
    "standard_rate",
    "valuation_rate",
    "last_purchase_rate",
    "incoming_rate",
    "default_bom",
    "custom_tfw_price",
    "pos_on_sale_price",
    "price_before_sale",
    "manufacturing_cost",
    "manufacturing_cost_source",
    "manufacturing_bom",
)

# Row fields that would let a line end up below the price list rate by any route other
# than the capped discount: margins and pricing rules stay off for partners.
ROW_LOCKED_FIELDS = {
    "margin_rate_or_amount": 0,
    "rate_with_margin": 0,
    "pricing_rules": "",
}

# A fresh line starts with no discount (item details for a row being added).
ROW_DISCOUNT_FIELDS = {"discount_percentage": 0, "discount_amount": 0, **ROW_LOCKED_FIELDS}


@contextmanager
def as_system_user():
    """Run ERPNext's own pricing code with its permission checks satisfied.

    ``get_item_details`` insists on read access to Sales Invoice, which partners must
    not have. Callers only use this after the customer has been checked against the
    partner's scope and the price list has been forced, and they price and scrub the
    result themselves.
    """
    original = frappe.session.user
    frappe.set_user("Administrator")
    try:
        yield
    finally:
        frappe.set_user(original)


def require_scoped_customer(customer) -> str:
    """The customer must be one of the partner's own; returns it."""
    if not customer:
        frappe.throw(_("Select a customer first."))

    if not is_customer_in_scope(customer, get_scope()["partners"]):
        frappe.throw(_("You are not permitted to do this."), frappe.PermissionError)

    return customer


def customer_base_list(customer):
    """The customer's own selling list, else their customer group's, else ``None``."""
    return frappe.db.get_value("Customer", customer, "default_price_list") or frappe.db.get_value(
        "Customer Group",
        frappe.db.get_value("Customer", customer, "customer_group"),
        "default_price_list",
    )


def resolve_pricing_context(customer, delivery_charge=None):
    """The one server-validated pricing context for a partner's customer and charge.

    Returns ``{price_list, fallback, charge}``. Every partner price read goes through
    this, so the item grid, item details, order saves, single-price lookups, offline
    deltas and the request gate cannot disagree. The charge is checked first (enabled,
    offered to partners here, same offer rules as the dropdown), then both lists must be
    enabled selling lists; a locked (container) charge never falls back.
    """
    from . import charge_pricing, price_resolution

    if not customer:
        frappe.throw(_("Select a customer first."))

    charge = charge_pricing.validated_partner_charge(delivery_charge, customer)
    base = customer_base_list(customer)
    price_list, fallback = price_resolution.resolve_lists(base, charge)
    if not price_list:
        bad = (charge.price_list if price_resolution.is_locked(charge) else base or (charge and charge.price_list))
        if not bad:
            frappe.throw(
                _("Customer {0} has no default price list. Ask Agile to set one before ordering.").format(
                    customer
                )
            )
        frappe.throw(_("Price list {0} is not an enabled selling price list.").format(bad))

    return frappe._dict(price_list=price_list, fallback=fallback, charge=charge)


def get_customer_price_list(customer, delivery_charge=None) -> str:
    """The selling price list for this customer and delivery charge, or a clear error."""
    return resolve_pricing_context(customer, delivery_charge).price_list


def get_price_list_rate(item_code, price_list, uom=None, conversion_factor=None, customer=None):
    """Item Price rate for ``item_code`` in ``uom``, or ``None`` when it has no price.

    Same Item Price selection as the POS grid (date, currency and customer filters,
    customer-specific rows winning). An exact UOM row is used as is; otherwise the
    stock UOM price is scaled by the conversion factor.
    """
    from .item_fetchers import _fetch_item_prices

    currency = frappe.db.get_value("Price List", price_list, "currency")
    rows = _fetch_item_prices(price_list, currency, (item_code,), customer or "", nowdate(), True)

    by_uom = {}
    for row in rows:
        by_uom[row.get("uom") or "None"] = row

    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
    if uom and uom in by_uom:
        return flt(by_uom[uom].get("price_list_rate"))

    base = by_uom.get(stock_uom) or by_uom.get("None")
    if not base:
        return None

    if not uom or uom == stock_uom:
        return flt(base.get("price_list_rate"))

    return flt(base.get("price_list_rate")) * (flt(conversion_factor) or 1.0)


def get_uom_rate(item_code, uom, customer, delivery_charge=None):
    """What a partner's customer pays per ``uom`` of an item, or ``None`` when unpriced."""
    require_scoped_customer(customer)
    context = resolve_pricing_context(customer, delivery_charge)
    conversion_factor = frappe.db.get_value(
        "UOM Conversion Detail", {"parent": item_code, "uom": uom}, "conversion_factor"
    )
    stock_uom = frappe.db.get_value("Item", item_code, "stock_uom")
    if uom != stock_uom and not conversion_factor:
        return None  # not a UOM this item is sold in

    rate = get_rate_with_fallback(
        item_code, context.price_list, context.fallback, uom, conversion_factor, customer
    )
    return rate if rate and rate > 0 else None


def get_rate_with_fallback(item_code, price_list, fallback, uom=None, conversion_factor=None, customer=None):
    """Rate from ``price_list``, or from ``fallback`` when the item has no price on it."""
    rate = get_price_list_rate(item_code, price_list, uom, conversion_factor, customer)
    if (not rate or rate <= 0) and fallback:
        rate = get_price_list_rate(item_code, fallback, uom, conversion_factor, customer)
    return rate


POS_EXCLUDE_FIELD = "custom_exclude_from_pos"
PARTNER_POS_EXCLUDE_FIELD = "agiletfw_exclude_from_partner_pos"


def exclusion_field():
    """The Item check field that hides an item from the POS in use, or None.

    The standard POS keeps using "Exclude from POS". The partner POS has its own
    "Exclude from Partner POS", so partner availability can differ from the standard POS
    without either one changing the other. Until the partner field exists on a site the
    partner POS falls back to the standard one.
    """
    if is_partner_user() and frappe.db.has_column("Item", PARTNER_POS_EXCLUDE_FIELD):
        return PARTNER_POS_EXCLUDE_FIELD
    if frappe.db.has_column("Item", POS_EXCLUDE_FIELD):
        return POS_EXCLUDE_FIELD
    return None


def is_unpriced(item, detail) -> bool:
    """True when a partner must not be offered ``item``: it has no price on their list.

    Templates are exempt: they have no price of their own, and their variants are
    priced (and dropped) individually.
    """
    if not is_partner_user() or item.get("has_variants"):
        return False

    return flt((detail or {}).get("price_list_rate")) <= 0


def scrub_item_row(row: dict) -> dict:
    """Drop cost and retail-override fields from an item row (in place)."""
    for field in HIDDEN_ITEM_FIELDS:
        row.pop(field, None)

    row["is_on_sale"] = False
    return row


def apply_item_detail(detail: dict, customer, uom=None, conversion_factor=None, delivery_charge=None) -> dict:
    """Price an ERPNext item-details result from the partner's price list (in place)."""
    require_scoped_customer(customer)
    context = resolve_pricing_context(customer, delivery_charge)
    price_list = context.price_list
    rate = get_rate_with_fallback(
        detail.get("item_code"),
        price_list,
        context.fallback,
        uom or detail.get("uom"),
        conversion_factor,
        customer,
    )
    if not rate or rate <= 0:
        frappe.throw(
            _("{0} has no price on price list {1}.").format(detail.get("item_code"), price_list)
        )

    detail["selling_price_list"] = price_list
    detail["price_list_rate"] = rate
    detail["rate"] = rate
    detail.update(ROW_DISCOUNT_FIELDS)
    return scrub_item_row(detail)


# What a partner's item-details request may pass to ERPNext's get_item_details. Anything
# else the browser sent (rate, price_list, buying price list, supplier, conversion rates,
# margins, pricing rules, ignore flags) is dropped, because the call runs as Administrator.
PARTNER_ITEM_ARGS = (
    "item_code",
    "qty",
    "uom",
    "conversion_factor",
    "warehouse",
    "batch_no",
    "serial_no",
    "has_batch_no",
    "has_serial_no",
    "is_stock_item",
    "pos_profile",
    "tax_category",
    "update_stock",
)


def sanitise_item_details_input(item, customer, delivery_charge, price_list, company):
    """``(item, doc)`` for ERPNext's get_item_details, built only from validated inputs."""
    clean = frappe._dict({key: item.get(key) for key in PARTNER_ITEM_ARGS if item.get(key) is not None})
    currency = frappe.db.get_value("Price List", price_list, "currency")
    clean.update(
        {
            "customer": customer,
            "selling_price_list": price_list,
            "currency": currency,
            "transaction_type": "selling",
            "doctype": "Sales Invoice",
            "name": "New Sales Invoice 1",
            "ignore_pricing_rule": 1,
            "conversion_rate": 1,
            "plc_conversion_rate": 1,
        }
    )
    if company:
        clean["company"] = company

    doc = frappe._dict(
        doctype="Sales Invoice",
        company=company,
        customer=customer,
        posa_delivery_charges=delivery_charge,
        selling_price_list=price_list,
        currency=currency,
        price_list_currency=currency,
        transaction_date=nowdate(),
    )
    return clean, doc


def neutralise_payment_fields(order: dict, data: dict | None = None) -> None:
    """Strip anything that would take payment or spend customer credit (in place).

    Partners place orders; they never collect money. The submit path creates Payment
    Entries and redeems credit straight from these payload fields.
    """
    for payload in (order, data):
        if not isinstance(payload, dict):
            continue

        payload["payments"] = []
        payload["redeemed_customer_credit"] = 0
        payload["sales_order_settlement_state"] = "none"
        payload["allow_no_payment_order_submit"] = 1
        # Nothing may arrive pre-paid either: advances are read-only fields a payload
        # could still try to set. ``payment_type`` is deliberately not touched here; the
        # submit validates it against the POS Profile (Paid is reset, On Account and
        # Proforma are no-payment types, so they are safe for a partner).
        payload["advance_paid"] = 0
        payload.pop("advances", None)


def enforce_sales_order_pricing(doc, method=None) -> None:
    """``Sales Order.before_validate``: reprice a partner's order from their price list."""
    if getattr(doc, "_action", None) == "update_after_submit" or cint(doc.docstatus) == 2:
        return

    if not is_partner_user():
        return

    customer = require_scoped_customer(doc.get("customer"))
    context = resolve_pricing_context(customer, doc.get("posa_delivery_charges"))
    price_list, fallback = context.price_list, context.fallback

    # Commission is the partner's pay, so the server decides it, never the browser: the
    # customer's own partner, and the customer's rate or else that partner's rate (the same
    # rule as the commission backfill). ERPNext alone would leave the rate at the customer's
    # 0 when the partner isn't in the payload, and would accept any rate a client sent.
    partner, customer_rate = frappe.db.get_value(
        "Customer", customer, ["default_sales_partner", "default_commission_rate"]
    )
    doc.sales_partner = partner
    doc.commission_rate = flt(customer_rate) or flt(
        frappe.db.get_value("Sales Partner", partner, "commission_rate")
    )

    doc.selling_price_list = price_list
    doc.ignore_pricing_rule = 1
    doc.coupon_code = ""

    # A partner may discount, up to the cap. The order-level discount comes off the net
    # total (before tax) so that "percent of the order" means the same thing everywhere;
    # the combined effect of row and order discounts is checked in enforce_discount_cap.
    header_percentage = flt(doc.get("additional_discount_percentage"))
    if header_percentage < 0 or header_percentage > PARTNER_MAX_DISCOUNT + DISCOUNT_TOLERANCE:
        frappe.throw(_("The order discount can't be more than {0}%.").format(PARTNER_MAX_DISCOUNT))
    if flt(doc.get("discount_amount")) < 0:
        frappe.throw(_("The order discount can't be negative."))
    doc.apply_discount_on = "Net Total"

    for row in [row for row in doc.get("items") or [] if cint(row.get("is_free_item"))]:
        doc.remove(row)

    for row in doc.get("items") or []:
        rate = get_rate_with_fallback(
            row.item_code, price_list, fallback, row.get("uom"), row.get("conversion_factor"), customer
        )
        if not rate or rate <= 0:
            frappe.throw(
                _("Row {0}: {1} has no price on price list {2}.").format(row.idx, row.item_code, price_list)
            )

        # A line's discount may be typed as a percentage or an amount; either way it is the
        # percentage that counts, and it can't be negative (a markup) or above the cap.
        percentage = flt(row.get("discount_percentage"))
        if not percentage and flt(row.get("discount_amount")) > 0:
            percentage = flt(row.get("discount_amount")) / rate * 100
        if percentage < 0 or percentage > PARTNER_MAX_DISCOUNT + DISCOUNT_TOLERANCE:
            frappe.throw(
                _("Row {0}: a discount of {1}% is more than the {2}% allowed.").format(
                    row.idx, flt(percentage, 2), PARTNER_MAX_DISCOUNT
                )
            )

        row.price_list_rate = rate
        row.discount_percentage = percentage
        row.discount_amount = 0
        row.rate = flt(rate * (1 - percentage / 100), 6)
        for field, value in ROW_LOCKED_FIELDS.items():
            row.set(field, value)


def effective_discount_percentage(doc) -> float:
    """What share of the order's price list value has been discounted away, in percent.

    Uses the totals ERPNext has already computed, so row discounts and the order-level
    discount (percentage or amount) are both counted, and compounding can't hide anything.
    """
    items = doc.get("items") or []
    list_total = sum(
        flt(row.get("base_price_list_rate") or row.get("price_list_rate")) * flt(row.get("qty"))
        for row in items
    )
    if list_total <= 0:
        return 0.0

    net_total = flt(doc.get("base_net_total") or doc.get("net_total"))
    return (1 - net_total / list_total) * 100


def enforce_discount_cap(doc, method=None) -> None:
    """``Sales Order.validate``: a partner's order can't be discounted past the cap.

    Runs after ERPNext has calculated the totals, so it sees the real outcome however the
    discount was entered.
    """
    if getattr(doc, "_action", None) == "update_after_submit" or cint(doc.docstatus) == 2:
        return

    if not is_partner_user():
        return

    discount = effective_discount_percentage(doc)
    if discount > PARTNER_MAX_DISCOUNT + DISCOUNT_TOLERANCE:
        frappe.throw(
            _("The total discount on this order is {0}%, which is more than the {1}% allowed.").format(
                flt(discount, 2), PARTNER_MAX_DISCOUNT
            )
        )
