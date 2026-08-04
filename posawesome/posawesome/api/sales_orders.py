# Copyright (c) 2020, Youssef Restom and contributors
# For license information, please see license.txt

import json
from copy import deepcopy
import secrets
import string
from collections import defaultdict

import frappe
from frappe import _
from erpnext.accounts.party import get_party_account
from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note, make_sales_invoice
from frappe.utils import cint, cstr, flt, getdate, nowdate, split_emails, validate_email_address

from posawesome.posawesome.api.payment_entry import create_payment_entry


_ORDER_REF_ALPHABET = string.ascii_uppercase + string.digits
MANAGED_SALES_ORDER_EXCLUDED_CUSTOMERS = {"13682"}
MANAGED_SALES_ORDER_UPDATE_FIELDS = {
    "customer_ref",
    "prefered_earliest_delivery_date",
    "preferred_earliest_delivery_date",
    "posa_notes",
}


def _generate_order_ref():
    return "OR" + "".join(secrets.choice(_ORDER_REF_ALPHABET) for _ in range(10))


def _is_customer_order_ref_in_use(order_ref, sales_order_name=None):
    normalized = str(order_ref or "").strip()
    if not normalized:
        return False

    matches = frappe.get_all(
        "Sales Order",
        filters={"customer_order_ref": normalized},
        pluck="name",
        limit=2,
    )
    if not matches:
        return False

    if sales_order_name:
        current_name = str(sales_order_name).strip()
        return any(str(name).strip() != current_name for name in matches)

    return True


def _ensure_unique_customer_order_ref(data, sales_order_name=None):
    if not isinstance(data, dict):
        return None

    requested = str(data.get("customer_order_ref") or "").strip()
    if requested and not _is_customer_order_ref_in_use(requested, sales_order_name):
        data["customer_order_ref"] = requested
        return requested

    for _ in range(20):
        candidate = _generate_order_ref()
        if not _is_customer_order_ref_in_use(candidate, sales_order_name):
            data["customer_order_ref"] = candidate
            return candidate

    frappe.throw(_("Unable to generate a unique order reference. Please try again."))


@frappe.whitelist()
def get_unique_order_ref(sales_order_name=None):
    payload = {}
    return _ensure_unique_customer_order_ref(payload, sales_order_name)


def _payment_entry_job(order_name, payments):
    """Background task to create payment entries."""
    so_doc = frappe.get_doc("Sales Order", order_name)
    _create_payment_entries(so_doc, payments)


def _split_payment_entry_job(order_name, payments):
    so_doc = frappe.get_doc("Sales Order", order_name)
    _create_payment_entries(so_doc, payments)


def _parse_cc_emails(raw):
    sanitized = validate_email_address(raw, throw=False)
    return split_emails(sanitized)


def _get_receipt_email_settings(profile_name):
    if not profile_name:
        return 0, "", []

    profile = frappe.get_cached_doc("POS Profile", profile_name)
    enabled = cint(getattr(profile, "posa_auto_email_receipt_on_submit", 0) or 0)
    print_format = str(getattr(profile, "posa_receipt_email_print_format", "") or "").strip()
    cc_emails = _parse_cc_emails(getattr(profile, "posa_receipt_email_cc", "") or "")
    return enabled, print_format, cc_emails


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
        return False, "", []

    if not getattr(so_doc, "pos_profile", None):
        return False, "", []

    enabled, print_format, cc_emails = _get_receipt_email_settings(so_doc.pos_profile)
    if not enabled:
        return False, "", []

    if not print_format:
        if log_skip:
            _log_receipt_skip(so_doc, "Receipt email is enabled but no print format is configured.")
        return False, "", []

    return True, print_format, cc_emails


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
    should_send, print_format, cc_emails = _should_auto_email_receipt(doc, log_skip=True)
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
        cc=cc_emails,
    )


def _send_receipt_email_job(sales_order_name, recipient, pos_profile=None, print_format=None, cc=None):
    try:
        frappe.logger().info(
            "POSAwesome receipt email: job start for Sales Order %s",
            sales_order_name,
        )
        so_doc = frappe.get_doc("Sales Order", sales_order_name)
        resolved_print_format = str(print_format or "").strip()
        cc_emails = list(cc or [])
        if not resolved_print_format and pos_profile:
            enabled, resolved_print_format, profile_cc_emails = _get_receipt_email_settings(pos_profile)
            if not enabled:
                frappe.logger().info(
                    "POSAwesome receipt email: job disabled by POS Profile for Sales Order %s",
                    sales_order_name,
                )
                return
            if not cc_emails:
                cc_emails = profile_cc_emails

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
            "POSAwesome receipt email: before sendmail for Sales Order %s recipient=%s cc=%s bytes=%s",
            sales_order_name,
            recipient,
            cc_emails,
            len(attachment.get("fcontent") or b""),
        )
        send_kwargs = dict(
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
        if cc_emails:
            send_kwargs["cc"] = cc_emails
        frappe.sendmail(**send_kwargs)
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
        "rfs_order": 1,
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


def _managed_sales_order_filters(company, currency, pos_profile=None):
    filters = {
        "docstatus": 1,
        "company": company,
        "currency": currency,
        "rfs_order": 1,
        "is_pos": 1,
        "customer": ["not in", sorted(MANAGED_SALES_ORDER_EXCLUDED_CUSTOMERS)],
    }
    if pos_profile:
        filters["pos_profile"] = pos_profile
    return filters


def _search_managed_sales_order_names(search_term, base_filters):
    """Sales Order names matching search_term on order name, customer name, payment ref, or postcode.

    base_filters scopes each lookup to the same company/currency/pos_profile/etc as
    the main listing query, so the search never surfaces orders outside that scope.
    """
    like_term = f"%{search_term}%"
    names = set()

    name_filters = dict(base_filters)
    name_filters["name"] = ["like", like_term]
    names.update(frappe.get_all("Sales Order", filters=name_filters, pluck="name", limit_page_length=0))

    customer_name_filters = dict(base_filters)
    customer_name_filters["customer_name"] = ["like", like_term]
    names.update(
        frappe.get_all("Sales Order", filters=customer_name_filters, pluck="name", limit_page_length=0)
    )

    customer_order_ref_filters = dict(base_filters)
    customer_order_ref_filters["customer_order_ref"] = ["like", like_term]
    names.update(
        frappe.get_all("Sales Order", filters=customer_order_ref_filters, pluck="name", limit_page_length=0)
    )

    address_names = frappe.get_all(
        "Address", filters={"pincode": ["like", like_term]}, pluck="name", limit_page_length=0
    )
    if address_names:
        customer_address_filters = dict(base_filters)
        customer_address_filters["customer_address"] = ["in", address_names]
        names.update(
            frappe.get_all(
                "Sales Order", filters=customer_address_filters, pluck="name", limit_page_length=0
            )
        )

        shipping_address_filters = dict(base_filters)
        shipping_address_filters["shipping_address_name"] = ["in", address_names]
        names.update(
            frappe.get_all(
                "Sales Order", filters=shipping_address_filters, pluck="name", limit_page_length=0
            )
        )

    return names


def _is_managed_sales_order_doc(doc):
    if not doc or cstr(getattr(doc, "doctype", "")).strip() != "Sales Order":
        return False
    if cint(getattr(doc, "docstatus", 0)) != 1:
        return False
    if cint(getattr(doc, "rfs_order", 0)) != 1:
        return False
    if cint(getattr(doc, "is_pos", 0)) != 1:
        return False
    return cstr(getattr(doc, "customer", "")).strip() not in MANAGED_SALES_ORDER_EXCLUDED_CUSTOMERS


def _validate_managed_sales_order_doc(doc):
    if not _is_managed_sales_order_doc(doc):
        frappe.throw(_("Sales Order is not available in POS management."))


def _get_sales_order_pick_list_links(doc):
    row_links = defaultdict(list)
    order_level_links = []
    rows = frappe.get_all(
        "Pick List Item",
        filters={"sales_order": doc.name},
        fields=["parent", "sales_order_item"],
        limit_page_length=0,
    )
    pick_list_names = sorted({cstr(row.get("parent") or "").strip() for row in rows if row.get("parent")})
    if not pick_list_names:
        return row_links, order_level_links

    status_rows = frappe.get_all(
        "Pick List",
        filters={"name": ("in", pick_list_names)},
        fields=["name", "status", "docstatus", "per_delivered"],
        limit_page_length=0,
    )
    statuses = {
        cstr((row.get("name") if isinstance(row, dict) else getattr(row, "name", "")) or "").strip(): row
        for row in status_rows
    }

    for row in rows:
        pick_list_name = cstr(row.get("parent") or "").strip()
        if not pick_list_name:
            continue

        pick_list = statuses.get(pick_list_name)
        if not pick_list:
            continue

        link_info = {
            "name": pick_list.get("name") if isinstance(pick_list, dict) else pick_list.name,
            "status": pick_list.get("status") if isinstance(pick_list, dict) else pick_list.status,
            "docstatus": pick_list.get("docstatus") if isinstance(pick_list, dict) else pick_list.docstatus,
            "per_delivered": flt(
                (pick_list.get("per_delivered") if isinstance(pick_list, dict) else pick_list.per_delivered)
                or 0
            ),
        }
        sales_order_item = cstr(row.get("sales_order_item") or "").strip()
        if sales_order_item:
            row_links[sales_order_item].append(link_info)
        else:
            order_level_links.append(link_info)

    for sales_order_item, links in row_links.items():
        row_links[sales_order_item] = sorted(links, key=lambda entry: (entry["name"], entry["status"] or ""))

    order_level_links = sorted(order_level_links, key=lambda entry: (entry["name"], entry["status"] or ""))
    return row_links, order_level_links


def _is_active_pick_list(link):
    return cstr(link.get("status") or "").strip() not in {"Cancelled", "Completed"}


def _build_managed_sales_order_item_lock(item, linked_pick_lists):
    picked_qty = flt(getattr(item, "picked_qty", 0) or 0)
    delivered_qty = flt(getattr(item, "delivered_qty", 0) or 0)
    active_pick_lists = [link for link in linked_pick_lists if _is_active_pick_list(link)]

    if picked_qty > 0:
        return {
            "picked_qty": picked_qty,
            "delivered_qty": delivered_qty,
            "is_locked": True,
            "lock_reason": _("Picked qty is greater than 0."),
        }

    if delivered_qty > 0:
        return {
            "picked_qty": picked_qty,
            "delivered_qty": delivered_qty,
            "is_locked": True,
            "lock_reason": _("Delivered qty is greater than 0."),
        }

    if active_pick_lists:
        label = ", ".join(
            f"{link['name']} ({cstr(link.get('status') or '').strip() or _('Unknown')})"
            for link in active_pick_lists
        )
        return {
            "picked_qty": picked_qty,
            "delivered_qty": delivered_qty,
            "is_locked": True,
            "lock_reason": _("Linked Pick Lists block editing: {0}").format(label),
        }

    return {
        "picked_qty": picked_qty,
        "delivered_qty": delivered_qty,
        "is_locked": False,
        "lock_reason": None,
    }


def _serialize_managed_sales_order(doc):
    items = []
    latest_component_due_date = None
    row_pick_lists, order_level_pick_lists = _get_sales_order_pick_list_links(doc)

    for item in getattr(doc, "items", []) or []:
        component_due_date = getattr(item, "component_due_date", None)
        parsed_component_due_date = getdate(component_due_date) if component_due_date else None
        if parsed_component_due_date and (
            latest_component_due_date is None or parsed_component_due_date > latest_component_due_date
        ):
            latest_component_due_date = parsed_component_due_date

        linked_pick_lists = list(row_pick_lists.get(item.name, []))
        seen_pick_lists = {entry["name"] for entry in linked_pick_lists}
        for order_level_link in order_level_pick_lists:
            if order_level_link["name"] in seen_pick_lists:
                continue
            linked_pick_lists.append(order_level_link)
            seen_pick_lists.add(order_level_link["name"])

        lock_meta = _build_managed_sales_order_item_lock(item, linked_pick_lists)

        items.append(
            {
                "name": item.name,
                "item_code": item.item_code,
                "item_name": item.item_name,
                "description": item.description,
                "warehouse": item.warehouse,
                "uom": item.uom,
                "qty": item.qty,
                "picked_qty": lock_meta["picked_qty"],
                "delivered_qty": item.delivered_qty,
                "rate": item.rate,
                "amount": item.amount,
                "conversion_factor": getattr(item, "conversion_factor", None),
                "delivery_date": item.delivery_date,
                "component_due_date": component_due_date,
                "quoted_date": getattr(item, "quoted_date", None),
                "posa_notes": getattr(item, "posa_notes", None),
                "is_locked": lock_meta["is_locked"],
                "lock_reason": lock_meta["lock_reason"],
                "linked_pick_lists": linked_pick_lists,
            }
        )

    order_total = flt(getattr(doc, "grand_total", None) or 0)
    advance_paid = flt(getattr(doc, "advance_paid", None) or 0)
    outstanding_balance = max(flt(order_total - advance_paid), 0)

    return {
        "name": doc.name,
        "customer": doc.customer,
        "customer_name": doc.customer_name,
        "status": doc.status,
        "transaction_date": doc.transaction_date,
        "delivery_date": getattr(doc, "delivery_date", None),
        "prefered_earliest_delivery_date": getattr(doc, "prefered_earliest_delivery_date", None),
        "customer_ref": getattr(doc, "customer_ref", None),
        "customer_order_ref": getattr(doc, "customer_order_ref", None),
        "posa_notes": getattr(doc, "posa_notes", None),
        "shopify_notes": getattr(doc, "shopify_notes", None),
        "auto_release_date": getattr(doc, "auto_release_date", None),
        "shipping_address_name": getattr(doc, "shipping_address_name", None),
        "customer_address": getattr(doc, "customer_address", None),
        "currency": getattr(doc, "currency", None),
        "grand_total": getattr(doc, "grand_total", None),
        "rounded_total": getattr(doc, "rounded_total", None),
        "advance_paid": advance_paid,
        "outstanding_balance": outstanding_balance,
        "modified": getattr(doc, "modified", None),
        "owner": getattr(doc, "owner", None),
        "latest_component_due_date": latest_component_due_date,
        "items": items,
    }


def _normalize_managed_sales_order_update_payload(data):
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        frappe.throw(_("Sales Order update payload must be an object."))

    normalized = {}

    if "customer_ref" in data:
        customer_ref = cstr(data.get("customer_ref") or "").strip()
        normalized["customer_ref"] = customer_ref or None

    if "posa_notes" in data:
        normalized["posa_notes"] = cstr(data.get("posa_notes") or "").strip() or None

    preferred_key_present = any(
        field in data for field in ("prefered_earliest_delivery_date", "preferred_earliest_delivery_date")
    )
    if preferred_key_present:
        preferred_value = data.get("prefered_earliest_delivery_date")
        if preferred_value in (None, ""):
            preferred_value = data.get("preferred_earliest_delivery_date")
        normalized["prefered_earliest_delivery_date"] = (
            str(getdate(preferred_value)) if preferred_value else None
        )

    return normalized


def _unwrap_managed_sales_order_payload(data):
    payload = data
    if isinstance(data, dict) and "data" in data and len(data) == 1:
        payload = data.get("data")
    if isinstance(payload, dict) and "data" in payload and len(payload) == 1:
        payload = payload.get("data")
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        frappe.throw(_("Sales Order update payload must be an object."))
    return payload


def _normalize_managed_sales_order_item_row(row):
    if not isinstance(row, dict):
        frappe.throw(_("Each Sales Order item update must be an object."))

    qty = flt(row.get("qty"))
    conversion_factor = flt(row.get("conversion_factor") or 1)
    normalized = {
        "docname": cstr(row.get("docname") or row.get("name") or "").strip() or None,
        "item_code": cstr(row.get("item_code") or "").strip(),
        "uom": cstr(row.get("uom") or "").strip() or None,
        "description": cstr(row.get("description") or "").strip() or None,
        "bom_no": cstr(row.get("bom_no") or "").strip() or None,
        "qty": qty,
        "conversion_factor": conversion_factor,
    }
    if normalized["qty"] <= 0:
        frappe.throw(_("Item {0}: Qty must be greater than 0.").format(normalized["item_code"] or _("Row")))
    if not normalized["item_code"]:
        frappe.throw(_("Item code is required for each Sales Order row."))
    if not normalized["uom"]:
        frappe.throw(_("Item {0}: UOM is required.").format(normalized["item_code"]))
    return normalized


def _normalize_existing_managed_sales_order_item_row(row):
    return {
        "docname": cstr(getattr(row, "name", "") or "").strip() or None,
        "item_code": cstr(getattr(row, "item_code", "") or "").strip(),
        "uom": cstr(getattr(row, "uom", "") or "").strip() or None,
        "description": cstr(getattr(row, "description", "") or "").strip() or None,
        "bom_no": cstr(getattr(row, "bom_no", "") or "").strip() or None,
        "qty": flt(getattr(row, "qty", 0)),
        "conversion_factor": flt(getattr(row, "conversion_factor", 0) or 1),
    }


def _validate_managed_sales_order_item_mutations(doc, normalized_items):
    row_pick_lists, order_level_pick_lists = _get_sales_order_pick_list_links(doc)
    order_level_active = [link for link in order_level_pick_lists if _is_active_pick_list(link)]
    if order_level_active:
        label = ", ".join(
            f"{link['name']} ({cstr(link.get('status') or '').strip() or _('Unknown')})"
            for link in order_level_active
        )
        frappe.throw(_("Linked Pick Lists block editing: {0}").format(label))

    existing_rows = {row.name: row for row in getattr(doc, "items", []) or [] if getattr(row, "name", None)}
    incoming_by_docname = {row["docname"]: row for row in normalized_items if row.get("docname")}

    for docname, row in existing_rows.items():
        lock_meta = _build_managed_sales_order_item_lock(row, row_pick_lists.get(docname, []))
        incoming_row = incoming_by_docname.get(docname)
        if incoming_row is None:
            if lock_meta["is_locked"]:
                frappe.throw(
                    _("Item {0} cannot be removed from POS. {1}").format(row.item_code, lock_meta["lock_reason"])
                )
            continue

        if not lock_meta["is_locked"]:
            continue

        if incoming_row != _normalize_existing_managed_sales_order_item_row(row):
            frappe.throw(
                _("Item {0} cannot be updated from POS. {1}").format(row.item_code, lock_meta["lock_reason"])
            )


@frappe.whitelist()
def update_managed_sales_order_items(data):
    payload = _unwrap_managed_sales_order_payload(data)
    sales_order_name = cstr(payload.get("name") or "").strip()
    if not sales_order_name:
        frappe.throw(_("Sales Order name is required."))

    doc = frappe.get_doc("Sales Order", sales_order_name)
    _validate_managed_sales_order_doc(doc)

    incoming_items = payload.get("items") or []
    if not isinstance(incoming_items, list):
        frappe.throw(_("Sales Order items payload must be a list."))

    existing_rows = {row.name: row for row in getattr(doc, "items", []) or [] if getattr(row, "name", None)}
    normalized_items = []
    for row in incoming_items:
        normalized = _normalize_managed_sales_order_item_row(row)
        docname = normalized.get("docname")
        if docname and docname in existing_rows:
            existing_row = existing_rows[docname]
            normalized["rate"] = flt(getattr(existing_row, "rate", 0))
            normalized["warehouse"] = cstr(getattr(existing_row, "warehouse", "") or "").strip() or None
            delivery_date = getattr(existing_row, "delivery_date", None)
            normalized["delivery_date"] = str(getdate(delivery_date)) if delivery_date else None
        else:
            normalized["rate"] = 0
            normalized["warehouse"] = None
            normalized["delivery_date"] = None
        normalized_items.append(normalized)
    _validate_managed_sales_order_item_mutations(doc, normalized_items)

    from customer_due_dates.api.update_child_qty_rate import update_child_qty_rate as update_sales_order_items

    update_sales_order_items(
        parent_doctype="Sales Order",
        trans_items=json.dumps(normalized_items),
        parent_doctype_name=sales_order_name,
        child_docname="items",
    )

    doc.reload()
    return _serialize_managed_sales_order(doc)


@frappe.whitelist()
def get_managed_sales_orders(company, currency, order_name=None, pos_profile=None, limit_page_length=50):
    filters = _managed_sales_order_filters(company, currency, pos_profile)

    search_term = cstr(order_name or "").strip()
    if search_term:
        matched_names = _search_managed_sales_order_names(search_term, filters)
        if not matched_names:
            return []
        filters["name"] = ["in", sorted(matched_names)]

    records = frappe.get_list(
        "Sales Order",
        filters=filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "status",
            "transaction_date",
            "prefered_earliest_delivery_date",
            "customer_ref",
            "customer_order_ref",
            "currency",
            "pos_profile",
            "grand_total",
            "rounded_total",
            "advance_paid",
            "modified",
        ],
        limit_page_length=cint(limit_page_length) or 50,
        order_by="modified desc",
    )
    for row in records:
        order_total = flt(row.get("grand_total") or 0)
        advance_paid = flt(row.get("advance_paid") or 0)
        row["outstanding_balance"] = max(flt(order_total - advance_paid), 0)
    return records


@frappe.whitelist()
def get_managed_sales_order_pos_profiles(company=None):
    """Enabled POS Profiles assigned to the current user, for the Sales Orders filter."""
    conditions = ["p.disabled = 0", "u.user = %(user)s"]
    values = {"user": frappe.session.user}
    if company:
        conditions.append("p.company = %(company)s")
        values["company"] = company

    return frappe.db.sql(
        f"""
        SELECT DISTINCT p.name, p.company, p.currency
        FROM `tabPOS Profile` p
        INNER JOIN `tabPOS Profile User` u ON u.parent = p.name
        WHERE {" AND ".join(conditions)}
        ORDER BY p.name
        """,
        values,
        as_dict=1,
    )


@frappe.whitelist()
def get_managed_sales_order(sales_order):
    doc = frappe.get_doc("Sales Order", sales_order)
    _validate_managed_sales_order_doc(doc)
    return _serialize_managed_sales_order(doc)


@frappe.whitelist()
def update_managed_sales_order(data):
    payload = _unwrap_managed_sales_order_payload(data)

    sales_order_name = cstr(payload.get("name") or "").strip()
    if not sales_order_name:
        frappe.throw(_("Sales Order name is required."))

    doc = frappe.get_doc("Sales Order", sales_order_name)
    _validate_managed_sales_order_doc(doc)

    updates = _normalize_managed_sales_order_update_payload(payload)
    if "customer_order_ref" in payload and cstr(payload.get("customer_order_ref") or "").strip():
        updates["customer_order_ref"] = cstr(payload.get("customer_order_ref") or "").strip()

    if not updates:
        return _serialize_managed_sales_order(doc)

    if updates.get("customer_order_ref") and _is_customer_order_ref_in_use(
        updates["customer_order_ref"], sales_order_name
    ):
        frappe.throw(_("Customer Order Ref is already in use on another Sales Order."))

    for fieldname, value in updates.items():
        setattr(doc, fieldname, value)

    if "posa_notes" in updates:
        _sync_shopify_notes_from_posa(doc)

    # Use the normal document save flow so submitted Sales Orders produce
    # field-level Version history rather than a generic "edited" activity entry.
    doc.flags.ignore_permissions = True
    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)

    doc.reload()
    return _serialize_managed_sales_order(doc)


@frappe.whitelist()
def pay_managed_sales_order_balance(
    sales_order, mode_of_payment, amount=None, reference_no=None, reference_date=None
):
    sales_order_name = cstr(sales_order or "").strip()
    mode = cstr(mode_of_payment or "").strip()
    if not sales_order_name:
        frappe.throw(_("Sales Order name is required."))
    if not mode:
        frappe.throw(_("Mode of Payment is required."))

    doc = frappe.get_doc("Sales Order", sales_order_name)
    _validate_managed_sales_order_doc(doc)

    order_total = flt(getattr(doc, "grand_total", None) or 0)
    advance_paid = flt(getattr(doc, "advance_paid", None) or 0)
    outstanding_balance = max(flt(order_total - advance_paid), 0)
    if outstanding_balance <= 0.001:
        frappe.throw(_("This Sales Order is already fully paid."))

    payment_amount = flt(amount)
    if payment_amount <= 0:
        frappe.throw(_("Payment amount must be greater than zero."))
    if payment_amount - outstanding_balance > 0.001:
        frappe.throw(_("Payment amount cannot exceed the remaining balance."))

    payment_entry = create_payment_entry(
        company=doc.company,
        customer=doc.customer,
        amount=payment_amount,
        currency=doc.currency,
        mode_of_payment=mode,
        reference_no=cstr(reference_no or "").strip() or doc.name,
        reference_date=reference_date or nowdate(),
        posting_date=nowdate(),
        submit=0,
    )
    payment_entry.append(
        "references",
        {
            "allocated_amount": payment_amount,
            "reference_doctype": "Sales Order",
            "reference_name": doc.name,
        },
    )
    payment_entry.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    payment_entry.save()
    payment_entry.submit()

    doc.reload()
    return {
        "sales_order": _serialize_managed_sales_order(doc),
        "payment_entry": payment_entry.name,
    }


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

    preferred_delivery_date = parse_date(
        data.get("prefered_earliest_delivery_date")
        or data.get("preferred_earliest_delivery_date")
    )
    if preferred_delivery_date:
        data["prefered_earliest_delivery_date"] = preferred_delivery_date
        data["preferred_earliest_delivery_date"] = preferred_delivery_date

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
    # Sales Order's `apply_discount_on` field defaults to "Grand Total" at the
    # doctype level, which pulls delivery charges (an "Actual" tax row) into the
    # discount base. POSAwesome always computes its discount against item totals
    # only, so force "Net Total" here to keep delivery charges undiscounted.
    so_doc.apply_discount_on = "Net Total"

    # Same issue with `disable_rounded_total`: it defaults to unchecked at the
    # doctype level and is never copied from the POS Profile, so ERPNext rounds
    # grand_total while POSAwesome (which never rounds) collects payment against
    # the unrounded figure. Mirror the POS Profile's setting so the two agree.
    if so_doc.get("pos_profile"):
        so_doc.disable_rounded_total = frappe.get_cached_value(
            "POS Profile", so_doc.pos_profile, "disable_rounded_total"
        )

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
        if item_code.lower().startswith("ns") and not item.get("warehouse"):
            item["warehouse"] = ns_warehouse


def _is_collection_delivery_charge_selected(so_doc):
    charge_name = str(getattr(so_doc, "posa_delivery_charges", "") or "").strip()
    if not charge_name:
        return False
    collection = frappe.get_cached_value("Delivery Charges", charge_name, "collection")
    return bool(flt(collection))


def _is_collect_from_store_delivery_charge_selected(so_doc):
    charge_name = str(getattr(so_doc, "posa_delivery_charges", "") or "").strip()
    if not charge_name:
        return False
    collect_from_store = frappe.get_cached_value("Delivery Charges", charge_name, "collect_from_store")
    return bool(flt(collect_from_store))


def _add_tag_ignore_permissions(doc, tag):
    """Tag a document without the write-permission recheck that Document.add_tag performs.

    Document.add_tag reloads the doc via frappe.get_lazy_doc and calls check_permission("write")
    on that fresh instance, which does not carry the ignore_permissions flag set on so_doc
    elsewhere in this module. For POS users without Sales Order write permission this raises a
    bare frappe.PermissionError, which frappe.desk.doctype.tag.tag.DocTags.update then mishandles
    (is_missing_column indexes into empty e.args), surfacing as an opaque IndexError instead.
    """
    if not frappe.db.exists("Tag", tag):
        frappe.get_doc({"doctype": "Tag", "name": tag}).insert(ignore_permissions=True)

    if not frappe.db.exists(
        "Tag Link", {"document_type": doc.doctype, "document_name": doc.name, "tag": tag}
    ):
        frappe.get_doc(
            {
                "doctype": "Tag Link",
                "document_type": doc.doctype,
                "document_name": doc.name,
                "title": doc.get_title() or "",
                "tag": tag,
            }
        ).insert(ignore_permissions=True)


def _apply_collect_from_store_tag(so_doc):
    if not _is_collect_from_store_delivery_charge_selected(so_doc):
        return

    _add_tag_ignore_permissions(so_doc, "Collect from Store")


def _apply_collection_flow_tag(so_doc):
    if not _is_collection_delivery_charge_selected(so_doc):
        return

    _add_tag_ignore_permissions(so_doc, "Taken on Day")


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
    data.pop("posa_split_groups", None)
    _ensure_unique_customer_order_ref(data, data.get("name"))
    so_doc = _save_sales_order_doc_from_payload(data)
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


def _normalize_split_groups(payload):
    raw_groups = payload.get("posa_split_groups")
    if not raw_groups:
        return []

    if isinstance(raw_groups, dict):
        iterable = raw_groups.values()
    elif isinstance(raw_groups, list):
        iterable = raw_groups
    else:
        return []

    groups = []
    for index, entry in enumerate(iterable, start=1):
        if not isinstance(entry, dict):
            continue
        group_id = str(entry.get("group_id") or entry.get("id") or "").strip()
        if not group_id:
            continue
        label = str(entry.get("label") or entry.get("name") or _("Group {0}").format(index)).strip()
        row_ids = []
        seen = set()
        for row_id in entry.get("row_ids") or []:
            normalized = str(row_id or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            row_ids.append(normalized)
        groups.append(
            {
                "group_id": group_id,
                "label": label or _("Group {0}").format(index),
                "row_ids": row_ids,
            }
        )
    return groups


def _is_split_group_submit(payload):
    return bool(
        cint((payload or {}).get("posa_split_delivery"))
        and _normalize_split_groups(payload)
    )


def _validate_split_groups(payload):
    groups = _normalize_split_groups(payload)
    if not groups:
        frappe.throw(_("Split order groups are required when Split Delivery is selected"))

    items = payload.get("items") or []
    item_row_ids = []
    seen_items = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        row_id = str(item.get("posa_row_id") or "").strip()
        if not row_id:
            frappe.throw(_("Every split order item must include a row id"))
        if row_id in seen_items:
            frappe.throw(_("Duplicate item row id found in split order payload: {0}").format(row_id))
        seen_items.add(row_id)
        item_row_ids.append(row_id)

    if not item_row_ids:
        frappe.throw(_("Split orders require at least one item"))

    assigned_to_group = {}
    for group in groups:
        row_ids = group.get("row_ids") or []
        if not row_ids:
            frappe.throw(_("Split group {0} has no items assigned").format(group.get("label")))
        for row_id in row_ids:
            if row_id not in seen_items:
                frappe.throw(_("Unknown split order row id: {0}").format(row_id))
            if row_id in assigned_to_group:
                frappe.throw(
                    _("Item row {0} is assigned to multiple split groups").format(row_id)
                )
            assigned_to_group[row_id] = group.get("group_id")

    missing_row_ids = [row_id for row_id in item_row_ids if row_id not in assigned_to_group]
    if missing_row_ids:
        frappe.throw(
            _("Every item must be assigned to a split group. Missing: {0}").format(
                ", ".join(missing_row_ids)
            )
        )

    item_map = {
        str(item.get("posa_row_id") or "").strip(): deepcopy(item)
        for item in items
        if isinstance(item, dict)
    }
    return groups, item_map


def _copy_group_order_payload(order, group, item_map, customer_order_ref):
    group_payload = deepcopy(order)
    group_payload.pop("name", None)
    group_payload.pop("amended_from", None)
    group_payload["items"] = [deepcopy(item_map[row_id]) for row_id in group.get("row_ids") or []]
    group_payload["posa_split_groups"] = []
    group_payload["must_be_fully_allocated"] = 1
    group_payload["posa_split_delivery"] = 0
    group_payload["customer_order_ref"] = customer_order_ref
    return group_payload


def _build_group_customer_order_ref(batch_root, group_index):
    root = str(batch_root or "").strip()
    suffix = f"{group_index:02d}"
    if not root:
        return None
    if len(root) >= 138:
        root = root[:138]
    return f"{root}-{suffix}"


def _allocate_group_payments(payments, orders, precision):
    allocations = {entry["group_id"]: [] for entry in orders}
    if not payments:
        return allocations

    totals = [flt(entry["grand_total"], precision) for entry in orders]
    total_amount = flt(sum(totals), precision)
    if total_amount <= 0:
        return allocations

    for payment in payments:
        if not isinstance(payment, dict):
            continue
        amount = flt(payment.get("amount"), precision)
        if amount == 0:
            continue

        allocated_sum = 0
        for index, entry in enumerate(orders):
            allocated = amount
            if index < len(orders) - 1:
                allocated = flt(amount * (totals[index] / total_amount), precision)
                allocated_sum = flt(allocated_sum + allocated, precision)
            else:
                allocated = flt(amount - allocated_sum, precision)

            allocated_payment = deepcopy(payment)
            allocated_payment["amount"] = allocated
            allocations[entry["group_id"]].append(allocated_payment)

    return allocations


def _save_sales_order_doc_from_payload(payload):
    payload = deepcopy(payload)
    payload.pop("posa_split_groups", None)
    if cint(payload.get("must_be_fully_allocated")):
        payload["must_be_fully_allocated"] = 1
    payload["is_pos"] = 1
    payload["pos_sales_person"] = (
        cstr(payload.get("pos_sales_person")).strip()
        or frappe.session.user
    )
    if payload.get("name") and frappe.db.exists("Sales Order", payload.get("name")):
        so_doc = frappe.get_doc("Sales Order", payload.get("name"))
        so_doc.update(payload)
    else:
        so_doc = frappe.get_doc(payload)

        from customer_due_dates.utils.rfs_customer import apply_sales_order_naming_series

        apply_sales_order_naming_series(so_doc, force=True)

    so_doc.flags.ignore_permissions = True
    frappe.flags.ignore_account_permission = True
    so_doc.docstatus = 0
    if cint(payload.get("must_be_fully_allocated")):
        so_doc.must_be_fully_allocated = 1
    _sync_shopify_notes_from_posa(so_doc)
    _apply_kit_meta_fields(so_doc)
    _apply_delivery_charges_tax_row(so_doc)
    so_doc.save()
    _apply_collection_flow_tag(so_doc)
    _apply_collect_from_store_tag(so_doc)
    return so_doc


def _build_split_group_documents(order):
    groups, item_map = _validate_split_groups(order)
    batch_root = _ensure_unique_customer_order_ref({"customer_order_ref": order.get("customer_order_ref")})
    built = []
    for index, group in enumerate(groups, start=1):
        preferred_ref = _build_group_customer_order_ref(batch_root, index)
        payload = _copy_group_order_payload(
            order,
            group,
            item_map,
            preferred_ref,
        )
        _ensure_unique_customer_order_ref(payload)
        so_doc = _save_sales_order_doc_from_payload(payload)
        so_doc.must_be_fully_allocated = 1
        so_doc.save()
        built.append(
            {
                "group_id": group["group_id"],
                "label": group["label"],
                "payload": payload,
                "doc": so_doc,
                "grand_total": getattr(so_doc, "rounded_total", 0) or getattr(so_doc, "grand_total", 0) or 0,
            }
        )
    return built


def _submit_split_group_documents(order):
    built_orders = _build_split_group_documents(order)
    payments = order.get("payments") or []
    precision = built_orders[0]["doc"].precision("grand_total") or 2
    total_paid = flt(sum(flt(payment.get("amount")) for payment in payments if isinstance(payment, dict)), precision)
    order_total = flt(order.get("rounded_total", 0) or order.get("grand_total", 0), precision)
    if total_paid <= 0 or order_total <= 0:
        settlement_state = "none"
    else:
        settlement_state = "full" if total_paid >= order_total - 0.001 else "deposit"
    payment_allocations = _allocate_group_payments(payments, built_orders, precision)

    for entry in built_orders:
        so_doc = entry["doc"]
        so_doc.submit()

        allocated_payments = payment_allocations.get(entry["group_id"]) or []
        if _should_create_collection_full_payment_synchronously(so_doc, settlement_state, allocated_payments):
            _create_payment_entries(so_doc, allocated_payments)
            _auto_create_delivery_note_for_non_ns_items(so_doc)
            continue

        _auto_create_delivery_note_for_non_ns_items(so_doc)
        if allocated_payments:
            frappe.enqueue(
                "posawesome.posawesome.api.sales_orders._split_payment_entry_job",
                queue="short",
                order_name=so_doc.name,
                payments=allocated_payments,
            )

    primary_doc = built_orders[0]["doc"]
    return {
        "name": primary_doc.name,
        "status": primary_doc.docstatus,
        "doctype": primary_doc.doctype,
        "names": [entry["doc"].name for entry in built_orders],
        "group_map": {entry["group_id"]: entry["doc"].name for entry in built_orders},
        "created_sales_orders": [
            {
                "name": entry["doc"].name,
                "doctype": entry["doc"].doctype,
                "status": entry["doc"].docstatus,
                "group_id": entry["group_id"],
                "label": entry["label"],
            }
            for entry in built_orders
        ],
    }


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


def _should_force_full_allocation_for_pos_order(order):
    return bool(cint((order or {}).get("posa_split_delivery")))


@frappe.whitelist()
def submit_sales_order(order, data=None):
    """Submit sales order and create payment entries."""
    order = json.loads(order)
    data = json.loads(data) if data else {}
    if data.get("sales_order_settlement_state") and not order.get("sales_order_settlement_state"):
        order["sales_order_settlement_state"] = data.get("sales_order_settlement_state")
    if data.get("allow_no_payment_order_submit") and not order.get("allow_no_payment_order_submit"):
        order["allow_no_payment_order_submit"] = data.get("allow_no_payment_order_submit")
    _map_delivery_dates(order)
    _apply_ns_default_warehouse(order)
    is_split_group_submit = _is_split_group_submit(order)
    if _should_force_full_allocation_for_pos_order(order):
        order["must_be_fully_allocated"] = 1
    if not is_split_group_submit:
        order.pop("posa_split_groups", None)
    _ensure_unique_customer_order_ref(order, order.get("name"))
    if is_split_group_submit:
        total_paid = 0
        for payment in order.get("payments") or []:
            if isinstance(payment, dict):
                total_paid += flt(payment.get("amount"))
        order_total = flt(order.get("rounded_total", 0) or order.get("grand_total", 0))
        settlement_state = _get_sales_order_settlement_state(
            {"payments": order.get("payments") or []},
            type(
                "SplitOrderSettlement",
                (),
                {
                    "rounded_total": order_total,
                    "grand_total": order_total,
                    "precision": lambda self, _fieldname: 2,
                },
            )(),
        )
        allow_no_payment_order_submit = cint(order.get("allow_no_payment_order_submit"))
        if settlement_state == "none" and not allow_no_payment_order_submit:
            frappe.throw(_("Please enter payment amount"))

        header_doc = type(
            "SplitOrderHeader",
            (),
            {
                "posa_delivery_charges": order.get("posa_delivery_charges"),
            },
        )()
        if settlement_state == "deposit" and _is_collection_delivery_charge_selected(header_doc):
            frappe.throw(_("Deposits are not allowed when a collection delivery charge is selected"))
        return _submit_split_group_documents(order)
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
    _apply_collection_flow_tag(so_doc)
    _apply_collect_from_store_tag(so_doc)

    settlement_state = _get_sales_order_settlement_state(order, so_doc)
    allow_no_payment_order_submit = cint(order.get("allow_no_payment_order_submit"))
    if settlement_state == "none" and not allow_no_payment_order_submit:
        frappe.throw(_("Please enter payment amount"))
    if settlement_state == "deposit" and _is_collection_delivery_charge_selected(so_doc):
        frappe.throw(_("Deposits are not allowed when a collection delivery charge is selected"))

    so_doc.submit()

    if _should_create_collection_full_payment_synchronously(so_doc, settlement_state, payments):
        _create_payment_entries(so_doc, payments)
        _auto_create_delivery_note_for_non_ns_items(so_doc)
        return {"name": so_doc.name, "status": so_doc.docstatus, "doctype": so_doc.doctype}

    _auto_create_delivery_note_for_non_ns_items(so_doc)

    if payments:
        frappe.enqueue(
            "posawesome.posawesome.api.sales_orders._payment_entry_job",
            queue="short",
            order_name=so_doc.name,
            payments=payments,
        )

    # Payment entries run in the background to speed up checkout

    return {"name": so_doc.name, "status": so_doc.docstatus, "doctype": so_doc.doctype}
