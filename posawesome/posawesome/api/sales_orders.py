# Copyright (c) 2020, Youssef Restom and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from erpnext.accounts.party import get_party_account
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice
from frappe.utils import cint, flt, getdate, nowdate

from posawesome.posawesome.api.payment_entry import create_payment_entry


def _payment_entry_job(order_name, payments):
    """Background task to create payment entries."""
    so_doc = frappe.get_doc("Sales Order", order_name)
    _create_payment_entries(so_doc, payments)


def _get_receipt_email_settings(profile_name):
    if not profile_name:
        return 0, ""

    profile = frappe.get_cached_doc("POS Profile", profile_name)
    enabled = cint(getattr(profile, "posa_auto_email_receipt_on_submit", 0) or 0)
    print_format = str(getattr(profile, "posa_receipt_email_print_format", "") or "").strip()
    return enabled, print_format


def _get_receipt_sender():
    email_account = frappe.get_cached_doc("Email Account", "ERP")
    return getattr(email_account, "email_id", None) or getattr(email_account, "default_sender", None) or ""


def _log_receipt_skip(so_doc, reason):
    frappe.log_error(
        f"Sales Order {getattr(so_doc, 'name', 'Unknown')}: {reason}",
        "POSAwesome Receipt Email Skipped",
    )


def _get_address_email(address_name):
    if not address_name:
        return ""

    email = frappe.db.get_value("Address", address_name, "email_id")
    return str(email or "").strip()


def _resolve_customer_email(so_doc):
    address_candidates = [
        getattr(so_doc, "customer_address", None),
        getattr(so_doc, "shipping_address_name", None),
    ]

    seen_addresses = set()
    for address_name in address_candidates:
        normalized = str(address_name or "").strip()
        if not normalized or normalized in seen_addresses:
            continue
        seen_addresses.add(normalized)
        email = _get_address_email(normalized)
        if email:
            return email

    email = frappe.db.get_value("Customer", so_doc.customer, "email_id") if so_doc.customer else None
    return str(email or "").strip()


def _get_print_format_override(print_format):
    records = frappe.get_all(
        "Print Format Overrides",
        filters={"print_format": print_format, "enabled": 1},
        fields=["height", "width"],
        limit=1,
    )
    return records[0] if records else None


def _build_receipt_attachment(so_doc, print_format):
    override = _get_print_format_override(print_format)
    height = override.get("height") if override else None
    width = override.get("width") if override else None

    if not (height and width):
        return frappe.attach_print(
            doctype=so_doc.doctype,
            name=so_doc.name,
            print_format=print_format,
            doc=so_doc,
        )

    from frappe.utils.pdf import get_pdf
    from frappe.utils.print_utils import get_print

    html = get_print(
        doctype=so_doc.doctype,
        name=so_doc.name,
        print_format=print_format,
        doc=so_doc,
    )
    size_css = (
        "<style>"
        ".print-format { "
        f"page-height: {height}cm; page-width: {width}cm; "
        "}"
        "</style>"
    )
    filename = str(so_doc.name).replace(" ", "").replace("/", "-") + ".pdf"
    return {"fname": filename, "fcontent": get_pdf(f"{size_css}\n{html}")}


def _should_auto_email_receipt(so_doc, log_skip=False):
    if not cint(getattr(so_doc, "is_pos", 0) or 0):
        return False, ""

    if not getattr(so_doc, "pos_profile", None):
        return False, ""

    enabled, print_format = _get_receipt_email_settings(so_doc.pos_profile)
    if not enabled:
        return False, ""

    if not print_format:
        if log_skip:
            _log_receipt_skip(so_doc, "Receipt email is enabled but no print format is configured.")
        return False, ""

    return True, print_format


def _is_dev_or_local_environment():
    site_name = str(getattr(getattr(frappe, "local", None), "site", "") or "").strip().lower()
    if site_name:
        return site_name.endswith(".local") or "local" in site_name or "dev" in site_name

    return False


def on_submit(doc, method):
    frappe.logger().info(
        "POSAwesome receipt email: on_submit start for Sales Order %s",
        getattr(doc, "name", "Unknown"),
    )
    should_send, print_format = _should_auto_email_receipt(doc, log_skip=True)
    frappe.logger().info(
        "POSAwesome receipt email: eligibility checked for Sales Order %s should_send=%s",
        getattr(doc, "name", "Unknown"),
        should_send,
    )
    if not should_send:
        return

    recipient = _resolve_customer_email(doc)
    frappe.logger().info(
        "POSAwesome receipt email: recipient resolved for Sales Order %s recipient=%s",
        getattr(doc, "name", "Unknown"),
        recipient or "<missing>",
    )
    if not recipient:
        _log_receipt_skip(doc, "Customer email is missing.")
        return

    if _is_dev_or_local_environment():
        frappe.logger().info(
            "POSAwesome receipt email: skipping send for local/dev site on Sales Order %s",
            getattr(doc, "name", "Unknown"),
        )
        return

    frappe.logger().info(
        "POSAwesome receipt email: queueing send for Sales Order %s",
        getattr(doc, "name", "Unknown"),
    )
    frappe.enqueue(
        "posawesome.posawesome.api.sales_orders._send_receipt_email_job",
        queue="short",
        enqueue_after_commit=True,
        sales_order_name=doc.name,
        recipient=recipient,
        pos_profile=doc.pos_profile,
        print_format=print_format,
    )


def _send_receipt_email_job(sales_order_name, recipient, pos_profile=None, print_format=None):
    try:
        frappe.logger().info(
            "POSAwesome receipt email: job start for Sales Order %s",
            sales_order_name,
        )
        so_doc = frappe.get_doc("Sales Order", sales_order_name)
        resolved_print_format = str(print_format or "").strip()
        if not resolved_print_format and pos_profile:
            enabled, resolved_print_format = _get_receipt_email_settings(pos_profile)
            if not enabled:
                frappe.logger().info(
                    "POSAwesome receipt email: job disabled by POS Profile for Sales Order %s",
                    sales_order_name,
                )
                return

        if not resolved_print_format:
            frappe.logger().info(
                "POSAwesome receipt email: job missing print format for Sales Order %s",
                sales_order_name,
            )
            return

        frappe.logger().info(
            "POSAwesome receipt email: before attach_print for Sales Order %s format=%s",
            sales_order_name,
            resolved_print_format,
        )
        attachment = _build_receipt_attachment(so_doc, resolved_print_format)
        frappe.logger().info(
            "POSAwesome receipt email: before sendmail for Sales Order %s recipient=%s bytes=%s",
            sales_order_name,
            recipient,
            len(attachment.get("fcontent") or b""),
        )
        frappe.sendmail(
            recipients=[recipient],
            sender=_get_receipt_sender(),
            subject=_("Your Receipt for Order - {0} - The Furniture Warehouse").format(
                so_doc.name
            ),
            message=_("Please find your receipt attached."),
            attachments=[attachment],
            reference_doctype=so_doc.doctype,
            reference_name=so_doc.name,
        )
        frappe.logger().info(
            "POSAwesome receipt email: after sendmail for Sales Order %s",
            sales_order_name,
        )
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            f"POSAwesome Receipt Email Error - Sales Order {sales_order_name}",
        )


@frappe.whitelist()
def search_orders(company, currency, order_name=None):
    filters = {
        "billing_status": ["in", ["Not Billed", "Partly Billed"]],
        "docstatus": 1,
        "company": company,
        "currency": currency,
    }
    if order_name:
        filters["name"] = ["like", f"%{order_name}%"]
    orders_list = frappe.get_list(
        "Sales Order",
        filters=filters,
        fields=["name"],
        limit_page_length=0,
        order_by="customer",
    )
    data = []
    for order in orders_list:
        data.append(frappe.get_doc("Sales Order", order["name"]))
    return data


def _map_delivery_dates(data):
    """Ensure mandatory delivery_date fields are populated."""

    def parse_date(value):
        if not value:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            if normalized.lower() in {"invalid date", "nan", "none", "null", "undefined"}:
                return None
            value = normalized
        try:
            return str(getdate(value))
        except Exception:
            return None

    # Map only explicit order-level delivery dates. Sales Order defaults should
    # apply when the POS flow does not provide one.
    order_delivery_date = (
        parse_date(data.get("delivery_date"))
        or parse_date(data.get("posa_delivery_date"))
    )
    if order_delivery_date:
        data["delivery_date"] = order_delivery_date

    # Map item level delivery dates
    for item in data.get("items", []):
        if not isinstance(item, dict):
            continue

        item_delivery = (
            parse_date(item.get("delivery_date"))
            or parse_date(item.get("posa_delivery_date"))
            or order_delivery_date
        )
        if item_delivery:
            item["delivery_date"] = item_delivery
            item.setdefault("posa_delivery_date", item_delivery)


def _apply_delivery_charges_tax_row(so_doc):
    """Mirror POS Awesome delivery-charge behavior for Sales Orders.

    Keeps Sales Taxes and Charges in sync with `posa_delivery_charges` selection.
    """
    old_doc = so_doc.get_doc_before_save() if not so_doc.is_new() else None
    old_charge_name = getattr(old_doc, "posa_delivery_charges", None) if old_doc else None
    current_charge_name = getattr(so_doc, "posa_delivery_charges", None)

    removable_descriptions = {d for d in [old_charge_name, current_charge_name] if d}
    recalc_needed = False

    if removable_descriptions and so_doc.get("taxes"):
        stale_rows = [
            row
            for row in so_doc.taxes
            if row.charge_type == "Actual" and row.description in removable_descriptions
        ]
        for row in stale_rows:
            so_doc.taxes.remove(row)
            recalc_needed = True

    if not current_charge_name:
        if hasattr(so_doc, "white_glove"):
            so_doc.white_glove = 0
        if recalc_needed:
            so_doc.calculate_taxes_and_totals()
        return

    charges_doc = frappe.get_cached_doc("Delivery Charges", current_charge_name)
    if hasattr(so_doc, "white_glove"):
        so_doc.white_glove = 1 if flt(getattr(charges_doc, "white_glove", 0)) else 0
    charge_rate = flt(getattr(so_doc, "posa_delivery_charges_rate", 0))
    if not charge_rate:
        profile_rate = next(
            (i.rate for i in charges_doc.profiles if i.pos_profile == so_doc.get("pos_profile")),
            None,
        )
        charge_rate = flt(profile_rate if profile_rate is not None else charges_doc.default_rate)
        conversion_rate = so_doc.get("conversion_rate") or 1
        charge_rate = flt(charge_rate / conversion_rate, so_doc.precision("posa_delivery_charges_rate"))
        so_doc.posa_delivery_charges_rate = charge_rate

    so_doc.append(
        "taxes",
        {
            "charge_type": "Actual",
            "description": current_charge_name,
            "tax_amount": charge_rate,
            "cost_center": charges_doc.cost_center,
            "account_head": charges_doc.shipping_account,
        },
    )
    so_doc.calculate_taxes_and_totals()


def _sync_shopify_notes_from_posa(so_doc):
    """Copy POS additional notes to Shopify notes when field exists."""
    if hasattr(so_doc, "shopify_notes"):
        so_doc.shopify_notes = getattr(so_doc, "posa_notes", None) or ""


def _apply_ns_default_warehouse(order_data):
    """Apply POS Profile default NS warehouse to NS-prefixed item codes."""
    if not isinstance(order_data, dict):
        return

    pos_profile = order_data.get("pos_profile")
    if not pos_profile:
        return

    ns_warehouse = frappe.db.get_value("POS Profile", pos_profile, "default_ns_warehouse")
    if not ns_warehouse:
        return

    for item in order_data.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        item_code = str(item.get("item_code") or "").strip()
        if item_code.lower().startswith("ns"):
            item["warehouse"] = ns_warehouse


def _is_collection_delivery_charge_selected(so_doc):
    charge_name = str(getattr(so_doc, "posa_delivery_charges", "") or "").strip()
    if not charge_name:
        return False
    collection = frappe.get_cached_value("Delivery Charges", charge_name, "collection")
    return bool(flt(collection))


def _auto_create_delivery_note_for_non_ns_items(so_doc):
    """Create and submit a Delivery Note from SO for NS items only."""
    if not _is_collection_delivery_charge_selected(so_doc):
        return None

    dn_doc = make_delivery_note(so_doc.name)
    if not dn_doc:
        return None

    filtered_items = []
    for row in dn_doc.get("items", []) or []:
        item_code = str(getattr(row, "item_code", "") or "").strip()
        if item_code.lower().startswith("ns"):
            filtered_items.append(row)

    dn_doc.set("items", filtered_items)
    if not dn_doc.items:
        return None

    dn_doc.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    dn_doc.insert()
    dn_doc.submit()
    return dn_doc.name


def _apply_kit_meta_fields(so_doc):
    """Mark kit parent metadata on Sales Order items (Shopify-compatible pattern)."""
    items = so_doc.get("items") or []
    if not items:
        return
    if not frappe.db.has_column("Item", "is_kit_item"):
        return

    item_codes = [str(getattr(row, "item_code", "") or "").strip() for row in items]
    item_codes = [code for code in item_codes if code]
    if not item_codes:
        return

    kit_rows = frappe.get_all(
        "Item",
        filters={"name": ["in", item_codes], "is_kit_item": 1},
        pluck="name",
    )
    kit_codes = set(kit_rows or [])
    if not kit_codes:
        return

    for row in items:
        item_code = str(getattr(row, "item_code", "") or "").strip()
        if item_code not in kit_codes:
            continue

        if hasattr(row, "is_kit_parent"):
            row.is_kit_parent = 1
        if hasattr(row, "is_kit_component"):
            row.is_kit_component = 0
        if hasattr(row, "kit_group_id") and not getattr(row, "kit_group_id", None):
            row.kit_group_id = frappe.generate_hash()
        if hasattr(row, "kit_parent_item_code"):
            row.kit_parent_item_code = item_code
        if hasattr(row, "kit_parent_row_idx"):
            row.kit_parent_row_idx = getattr(row, "idx", None)
        if hasattr(row, "kit_qty_factor"):
            row.kit_qty_factor = 1


@frappe.whitelist()
def update_sales_order(data):
    """Create or update a Sales Order document."""
    data = json.loads(data)
    _map_delivery_dates(data)
    _apply_ns_default_warehouse(data)
    if data.get("name") and frappe.db.exists("Sales Order", data.get("name")):
        so_doc = frappe.get_doc("Sales Order", data.get("name"))
        so_doc.update(data)
    else:
        so_doc = frappe.get_doc(data)

    so_doc.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    so_doc.docstatus = 0
    _sync_shopify_notes_from_posa(so_doc)
    _apply_kit_meta_fields(so_doc)
    _apply_delivery_charges_tax_row(so_doc)
    so_doc.save()
    return so_doc


def _create_payment_entries(so_doc, payments):
    """Create payment entries referencing the sales order."""
    for pay in payments or []:
        if not pay.get("amount"):
            continue

        reference_no = (
            pay.get("reference_no")
            or pay.get("transaction_id")
            or pay.get("authorization_code")
            or so_doc.get("posa_authorization_code")
            or so_doc.get("posa_pos_opening_shift")
            or so_doc.name
        )
        reference_date = pay.get("reference_date") or nowdate()

        # Create payment entry using helper to ensure exchange rates are set
        pe = create_payment_entry(
            company=so_doc.company,
            customer=so_doc.customer,
            amount=pay.get("amount"),
            currency=pay.get("currency") or so_doc.currency,
            mode_of_payment=pay.get("mode_of_payment"),
            reference_no=reference_no,
            reference_date=reference_date,
            posting_date=nowdate(),
            submit=0,
        )

        # Link payment entry to the sales order
        pe.append(
            "references",
            {
                "allocated_amount": pay.get("amount"),
                "reference_doctype": "Sales Order",
                "reference_name": so_doc.name,
            },
        )

        pe.flags.ignore_permissions = True
        frappe.flags.ignore_account_permission = True
        pe.save()
        pe.submit()


def _get_sales_order_settlement_state(order, so_doc):
    stated = str((order or {}).get("sales_order_settlement_state") or "").strip().lower()
    if stated in {"none", "deposit", "full"}:
        return stated

    total_paid = 0
    for payment in (order or {}).get("payments") or []:
        total_paid += flt(payment.get("amount"))

    order_total = flt(getattr(so_doc, "rounded_total", 0) or getattr(so_doc, "grand_total", 0))
    precision = so_doc.precision("rounded_total") or so_doc.precision("grand_total") or 2
    total_paid = flt(total_paid, precision)
    order_total = flt(order_total, precision)

    if total_paid <= 0 or order_total <= 0:
        return "none"

    return "full" if total_paid >= order_total - 0.001 else "deposit"


def _should_create_collection_full_payment_synchronously(so_doc, settlement_state, payments):
    return (
        settlement_state == "full"
        and bool(payments)
        and _is_collection_delivery_charge_selected(so_doc)
    )


@frappe.whitelist()
def submit_sales_order(order, data=None):
    """Submit sales order and create payment entries."""
    order = json.loads(order)
    data = json.loads(data) if data else {}
    if data.get("sales_order_settlement_state") and not order.get("sales_order_settlement_state"):
        order["sales_order_settlement_state"] = data.get("sales_order_settlement_state")
    _map_delivery_dates(order)
    _apply_ns_default_warehouse(order)
    if order.get("name") and frappe.db.exists("Sales Order", order.get("name")):
        so_doc = frappe.get_doc("Sales Order", order.get("name"))
        so_doc.update(order)
    else:
        so_doc = frappe.get_doc(order)

    payments = order.get("payments")

    so_doc.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    _sync_shopify_notes_from_posa(so_doc)
    _apply_kit_meta_fields(so_doc)
    _apply_delivery_charges_tax_row(so_doc)
    so_doc.save()

    settlement_state = _get_sales_order_settlement_state(order, so_doc)
    if settlement_state == "none":
        frappe.throw(_("Please enter payment amount"))
    if settlement_state == "deposit" and _is_collection_delivery_charge_selected(so_doc):
        frappe.throw(_("Deposits are not allowed when a collection delivery charge is selected"))

    so_doc.submit()

    if _should_create_collection_full_payment_synchronously(so_doc, settlement_state, payments):
        _create_payment_entries(so_doc, payments)
        _auto_create_delivery_note_for_non_ns_items(so_doc)
        return {"name": so_doc.name, "status": so_doc.docstatus}

    _auto_create_delivery_note_for_non_ns_items(so_doc)

    if payments:
        frappe.enqueue(
            "posawesome.posawesome.api.sales_orders._payment_entry_job",
            queue="short",
            order_name=so_doc.name,
            payments=payments,
        )

    # Payment entries run in the background to speed up checkout

    return {"name": so_doc.name, "status": so_doc.docstatus}
