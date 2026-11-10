"""Request gate for the locked-down Sales Partner POS (AP-1).

A *partner user* is identified by the ``posa_user_scope`` hook (implemented by
customer_due_dates), which returns ``{"is_partner": bool, "partners": [...]}``.
Without that hook nobody is a partner and this module does nothing.

For a partner user every request is checked in :func:`enforce` (``before_request``):

* Methods from apps other than Frappe are **default-deny**; only the allow-list in
  ``POS_METHODS`` gets through. Many POS endpoints bypass permissions with
  ``ignore_permissions``, so they cannot rely on Frappe's own checks.
* Frappe framework methods are permission-checked by Frappe against the partner's
  narrow role and the row scoping in customer_due_dates, so they are allowed, apart
  from the write paths in ``FRAMEWORK_DENIED``. Partners write only through the POS
  Sales Order endpoints.
* Allowed endpoints that take a customer or Sales Order are checked here, so the
  endpoint code needs no per-function scope logic: a customer must belong to one of
  the partner's Sales Partners, and so must the customer of any order referenced.
* ``/api/resource`` and ``/api/v2`` document routes are read-only.
"""

from __future__ import annotations

import json

import frappe
from frappe import _

API = "posawesome.posawesome.api."

READ_HTTP_METHODS = ("GET", "HEAD", "OPTIONS")

# Sentinel used when a partner user has no Sales Partner linked: matches no customer.
NO_PARTNER = "__no_sales_partner__"

# --- argument rules --------------------------------------------------------------
# customer: name of an argument holding a Customer ("optional" may be blank).
# order: name of an argument holding a Sales Order name (always required).
# payload: names of arguments holding a Sales Order document as JSON.
OPTIONAL_CUSTOMER = {"customer": "optional"}
REQUIRED_CUSTOMER = {"customer": "required"}
ORDER_NAME = {"order": "sales_order"}
SELF_USER = {"self_user": "user"}
ORDER_PAYLOAD_DATA = {"payload": ("data",)}
ORDER_PAYLOAD_ORDER = {"payload": ("order",)}


def _methods(prefix: str, names: dict[str, dict]) -> dict[str, dict]:
    return {f"{API}{prefix}{name}": rule for name, rule in names.items()}


# Dotted names are exactly what the POS frontend calls (items.* and invoices.* are
# re-exports of item_processing / invoice_processing).
POS_METHODS: dict[str, dict] = {
    **_methods(
        "utils.",
        {"get_active_pos_profile": {}, "get_default_warehouse": {}},
    ),
    **_methods(
        "utilities.",
        {
            "get_app_info": {},
            "get_available_languages": {},
            "get_build_info": {},
            "get_current_user_language": {},
            "get_language_info": {},
            "get_language_options": {},
            "get_pos_profile_tax_inclusive": {},
            "get_sales_person_names": {},
            "get_selling_price_lists": {},
            "get_translation_dict": {},
            "set_current_user_language": {},
            "log_client_error": {},
        },
    ),
    **_methods(
        "items.",
        {
            "get_item_brand": {},
            "get_available_qty": {},
            "get_item_detail": {},
            "get_items_count": {},
            "get_items_groups": {},
            "get_items_from_barcode": {},
            "get_price_for_uom": {},
            "parse_scale_barcode": {},
            "search_serial_or_batch_or_barcode_number": {},
            "get_delta_items": OPTIONAL_CUSTOMER,
            "get_item_variants": OPTIONAL_CUSTOMER,
            "get_items": OPTIONAL_CUSTOMER,
            "get_items_details": OPTIONAL_CUSTOMER,
            "search_items": OPTIONAL_CUSTOMER,
            "search_items_by_code": OPTIONAL_CUSTOMER,
        },
    ),
    **_methods("item_processing.search.", {"item_advanced_search_query": {}}),
    **_methods(
        "invoices.",
        {
            "fetch_exchange_rate_pair": {},
            "get_available_currencies": {},
            "get_price_list_currency": {},
            "validate_cart_items": {},
        },
    ),
    # No offers or pricing rules: a partner pays the price list rate, so the POS must never
    # show a promotional discount that the server would strip on save.
    **_methods("offers.", {"get_applicable_delivery_charges": OPTIONAL_CUSTOMER}),
    **_methods("print_formats.", {"get_print_formats": {}}),
    **_methods("bundles.", {"get_bundle_components": {}}),
    **_methods("kit_due_tree.", {"get_kit_due_tree": {}}),
    **_methods("yellow_ticket_photos.", {"get_requirements": {}}),
    **_methods("shifts.", {"check_opening_shift": SELF_USER}),
    # The terminal lock: a partner can set and use their own PIN, never anyone else's.
    # get_terminal_employees lists only the caller for a partner (see employees.py).
    **_methods(
        "employees.",
        {
            "get_terminal_employees": {},
            "get_cashier_pin_status": SELF_USER,
            "save_cashier_pin": SELF_USER,
            "verify_terminal_employee_pin": SELF_USER,
        },
    ),
    **_methods(
        "offline_sync.",
        {
            "bootstrap.sync_bootstrap_config": {},
            "currencies.sync_currency_scope": {},
            "customers.sync_customers": {},
            "items.sync_items": OPTIONAL_CUSTOMER,
            "payment_methods.sync_payment_method_currencies": {},
            "stock.sync_stock": {},
        },
    ),
    **_methods(
        "customers.",
        {
            "search_customers": {},
            "get_customer_names": {},
            "get_customers_count": {},
            "get_sales_person_names": {},
            "get_store_collection_addresses": {},
            "get_customer_info": REQUIRED_CUSTOMER,
            "get_customer_addresses": REQUIRED_CUSTOMER,
        },
    ),
    **_methods("customer.", {"get_customer_balance": REQUIRED_CUSTOMER}),
    **_methods(
        "sales_orders.",
        {
            "get_managed_sales_orders": {},
            "get_managed_sales_order_statuses": {},
            "get_managed_sales_order_pos_profiles": {},
            "get_unique_order_ref": {},
            "get_managed_sales_order": ORDER_NAME,
            "get_pos_order_summary": ORDER_NAME,
            "get_managed_sales_order_new_item_details": ORDER_NAME,
            "update_sales_order": ORDER_PAYLOAD_DATA,
            "update_managed_sales_order": ORDER_PAYLOAD_DATA,
            "update_managed_sales_order_items": ORDER_PAYLOAD_DATA,
            "preview_managed_sales_order_items": ORDER_PAYLOAD_DATA,
            "submit_sales_order": ORDER_PAYLOAD_ORDER,
            "preview_quoted_delivery_window": ORDER_PAYLOAD_ORDER,
            "preview_split_group_delivery_windows": ORDER_PAYLOAD_ORDER,
        },
    ),
    # Not in the posawesome API but called by the POS client.
    "erpnext.setup.utils.get_exchange_rate": {},
    "erpnext.controllers.queries.item_query": {},
}

# Handler shorthands (no dots) that a signed-in partner may still call. "login" is here
# because Frappe's LoginManager authenticates while the request is being set up, so by
# the time before_request runs, a partner signing in is already the session user.
SHORTHAND_ALLOWED = ("login", "logout", "web_logout", "ping")

# Framework methods that write, or reach outside the partner's data, even though
# Frappe would permission-check them. Partners change data only through the POS
# endpoints above. Entries ending in "." are prefixes.
FRAMEWORK_DENIED = (
    "frappe.client.insert",
    "frappe.client.insert_many",
    "frappe.client.save",
    "frappe.client.set_value",
    "frappe.client.submit",
    "frappe.client.cancel",
    "frappe.client.delete",
    "frappe.client.bulk_update",
    "frappe.client.rename_doc",
    "frappe.client.set_default",
    "frappe.client.attach_file",
    "frappe.client.get_password",
    "frappe.desk.form.save.",
    "frappe.desk.form.assign_to.",
    "frappe.desk.form.document_follow.",
    "frappe.desk.form.utils.",
    "frappe.desk.like.",
    "frappe.desk.reportview.delete_items",
    "frappe.desk.reportview.save_report",
    "frappe.desk.reportview.export_query",
    "frappe.handler.",
    "frappe.model.workflow.",
    "frappe.share.",
    "frappe.email.",
    "frappe.core.doctype.data_import.",
    "frappe.core.doctype.data_export.",
    "frappe.core.doctype.user.user.",
)

# Exceptions to FRAMEWORK_DENIED.
FRAMEWORK_ALLOWED = ("frappe.core.doctype.user.user.switch_theme",)


# The most a partner may take off, as a percentage of the price list value of an order.
# Enforced on the server (partner_pricing.enforce_discount_cap) and mirrored to the POS
# through the profile below, so the controls stop at the same number.
PARTNER_MAX_DISCOUNT = 50

# POS Profile settings forced for a partner, in the profile the browser receives. The
# frontend already honours these flags, so it simply shows no price, discount, return or
# payment controls. The server enforces the same rules independently.
PARTNER_PROFILE_LOCKS = {
    # Not one of the partner's customers; they choose their own.
    "customer": None,
    "posa_force_price_from_customer_price_list": 1,
    "posa_allow_user_to_edit_rate": 0,
    "posa_allow_user_to_edit_item_discount": 1,
    "posa_allow_user_to_edit_additional_discount": 1,
    "posa_allow_price_list_rate_change": 0,
    "posa_enable_price_list_dropdown": 0,
    "posa_max_discount_allowed": PARTNER_MAX_DISCOUNT,
    "posa_allow_change_posting_date": 0,
    "posa_allow_return": 0,
    "posa_allow_return_without_invoice": 0,
    "posa_use_gift_cards": 0,
    "posa_allow_credit_sale": 0,
    "posa_allow_write_off_change": 0,
    "posa_allow_customer_claims": 0,
    "posa_enable_customer_display": 0,
    "posa_silent_print": 0,
}


def lock_pos_profile(profile) -> None:
    """Apply ``PARTNER_PROFILE_LOCKS`` to a POS Profile document or dict (in place)."""
    for key, value in PARTNER_PROFILE_LOCKS.items():
        if isinstance(profile, dict):
            profile[key] = value
        else:
            profile.set(key, value)


def deny() -> None:
    frappe.throw(_("You are not permitted to do this."), frappe.PermissionError)


def get_scope(user: str | None = None) -> dict:
    """Partner scope for ``user`` from the ``posa_user_scope`` hook(s)."""
    user = user or frappe.session.user
    is_partner = False
    partners: set[str] = set()
    for hook in frappe.get_hooks("posa_user_scope"):
        scope = frappe.get_attr(hook)(user) or {}
        if scope.get("is_partner"):
            is_partner = True
            partners.update(scope.get("partners") or [])

    return {"is_partner": is_partner, "partners": sorted(partners)}


def is_partner_user(user: str | None = None) -> bool:
    return get_scope(user)["is_partner"]


def customer_scope_partners(user: str | None = None) -> list[str] | None:
    """Partners to filter customers by, or ``None`` when no scoping applies.

    A partner user with no linked partner gets a sentinel that matches nothing.
    """
    scope = get_scope(user)
    if not scope["is_partner"]:
        return None

    return scope["partners"] or [NO_PARTNER]


def is_customer_in_scope(customer, partners: list[str]) -> bool:
    if not isinstance(customer, str) or not customer or not partners:
        return False

    return frappe.db.get_value("Customer", customer, "default_sales_partner") in partners


def _requested_method(path: str, form) -> str | None:
    # Frappe prefers ``cmd`` over the path, and runs only the part before any "/".
    method = form.get("cmd")
    if not method:
        for prefix in ("/api/method/", "/api/v2/method/"):
            if path.startswith(prefix):
                method = path[len(prefix) :]
                break

    if not method:
        return None

    return str(method).split("/")[0].strip()


def _framework_denied(method: str) -> bool:
    if method in FRAMEWORK_ALLOWED:
        return False

    return any(
        method.startswith(entry) if entry.endswith(".") else method == entry for entry in FRAMEWORK_DENIED
    )


def _rule_for(method: str) -> dict:
    if method in POS_METHODS:
        return POS_METHODS[method]

    if method in SHORTHAND_ALLOWED:
        return {}

    if method.startswith("frappe.") and not _framework_denied(method):
        return {}

    deny()


def _check_customer_arg(form, arg: str, mode: str, partners: list[str]) -> None:
    value = form.get(arg)
    if value in (None, "") and mode == "optional":
        return

    if not is_customer_in_scope(value, partners):
        deny()


def _order_customer(order_name):
    if not isinstance(order_name, str) or not order_name:
        return None

    return frappe.db.get_value("Sales Order", order_name, "customer")


def _load_payload(raw) -> dict:
    # Mirrors the endpoints' own unwrapping of {"data": {"data": {...}}} wrappers.
    payload = raw
    for _i in range(2):
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                deny()
        if isinstance(payload, dict) and list(payload) == ["data"]:
            payload = payload["data"]

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            deny()

    if not isinstance(payload, dict):
        deny()

    return payload


def _check_payload(raw, partners: list[str]) -> None:
    payload = _load_payload(raw)

    customer = payload.get("customer")
    if customer not in (None, "") and not is_customer_in_scope(customer, partners):
        deny()

    name = payload.get("name")
    existing_customer = _order_customer(name) if name else None
    if existing_customer:
        # Updating an existing order: it must already belong to the partner.
        if not is_customer_in_scope(existing_customer, partners):
            deny()
    elif customer in (None, ""):
        # A new order must name an in-scope customer.
        deny()

    groups = payload.get("posa_split_groups")
    if isinstance(groups, dict):
        groups = list(groups.values())
    for group in groups if isinstance(groups, list) else []:
        group_customer = group.get("customer") if isinstance(group, dict) else None
        if group_customer not in (None, "") and not is_customer_in_scope(group_customer, partners):
            deny()


def check_request(scope: dict, path: str, http_method: str, form) -> None:
    """Raise PermissionError unless a partner user may make this request."""
    method = _requested_method(path, form)

    if method is None:
        # Document routes (/api/resource, /api/v2/document, ...) are read-only.
        if path.startswith("/api/") and http_method.upper() not in READ_HTTP_METHODS:
            deny()
        return

    rule = _rule_for(method)
    partners = scope["partners"]

    if rule.get("self_user") and form.get(rule["self_user"]) != frappe.session.user:
        # Otherwise a partner could read another user's shift, profile and company.
        deny()

    if rule.get("customer"):
        _check_customer_arg(form, "customer", rule["customer"], partners)

    if rule.get("order"):
        if not is_customer_in_scope(_order_customer(form.get(rule["order"])), partners):
            deny()

    for arg in rule.get("payload", ()):
        _check_payload(form.get(arg), partners)


def extend_boot(bootinfo) -> None:
    """``extend_bootinfo``: tell the POS frontend it is in partner mode.

    The frontend mirrors this exact allow-list (so it never fires a call the server
    would refuse) instead of keeping a second copy that could drift.
    """
    scope = get_scope()
    if not scope["is_partner"]:
        return

    bootinfo.posa_partner_mode = {
        "partners": scope["partners"],
        "allowed_methods": sorted(POS_METHODS),
        # Methods whose price or data depends on the customer; the browser supplies the
        # selected customer to any of these that omit it.
        "customer_methods": sorted(name for name, rule in POS_METHODS.items() if rule.get("customer")),
        "shorthand_allowed": list(SHORTHAND_ALLOWED),
        "framework_denied": list(FRAMEWORK_DENIED),
        "framework_allowed": list(FRAMEWORK_ALLOWED),
    }


def enforce() -> None:
    """``before_request`` hook."""
    user = frappe.session.user
    if not user or user == "Guest":
        return

    scope = get_scope(user)
    if not scope["is_partner"]:
        return

    request = frappe.local.request
    try:
        check_request(scope, request.path, request.method, frappe.form_dict)
    except frappe.PermissionError:
        # Warning level on purpose: frappe.logger defaults to WARNING, so info() is dropped.
        # The log is how a legitimate call that the allow-list missed gets found.
        frappe.logger("partner_gate").warning(f"denied {user} {request.method} {request.path}")
        raise
