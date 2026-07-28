"""Expose API functions for POS Awesome."""

from pypika.functions import Function


def _ensure_frappe_query_builder_year():
    """Provide a compatibility shim for benches missing frappe.query_builder.custom.Year."""
    try:
        from frappe.query_builder import custom as qb_custom
    except Exception:
        return

    if hasattr(qb_custom, "Year"):
        return

    class Year(Function):
        def __init__(self, field, alias=None):
            super().__init__("YEAR", field, alias=alias)

    qb_custom.Year = Year


_ensure_frappe_query_builder_year()

from .bundles import get_bundle_components
from .dashboard import get_dashboard_data
from .customers import (
    create_customer,
    get_customer_addresses,
    get_customer_info,
    get_customer_names,
    get_customers_count,
    get_store_collection_addresses,
    get_sales_person_names,
    link_store_collection_address_to_customer,
    make_address,
    set_customer_info,
)
from .invoices import (
    delete_invoice,
    get_draft_invoices,
    get_last_invoice_rates,
    search_invoices_for_return,
    submit_invoice,
    update_invoice,
    validate_return_items,
)
from .items import (
    build_scale_barcode,
    get_item_attributes,
    get_item_brand,
    get_item_detail,
    get_items,
    get_items_count,
    get_items_details,
    get_items_from_barcode,
    search_items,
    parse_scale_barcode,
    get_items_groups,
)
from .offers import (
    get_active_gift_coupons,
    get_applicable_delivery_charges,
    get_offers,
    get_pos_coupon,
)
from .payments import (
    create_payment_request,
    get_available_credit,
)
from .stored_value import (
    get_available_stored_value,
    get_stored_value_summary,
)
from .sales_orders import (
    get_managed_sales_order,
    get_managed_sales_orders,
    get_unique_order_ref,
    search_orders,
    submit_sales_order,
    update_managed_sales_order,
    update_managed_sales_order_items,
    update_sales_order,
)
from .quotations import (
    submit_quotation,
    update_quotation,
)
from .purchase_orders import (
    create_purchase_item,
    create_purchase_order,
    create_supplier,
    search_suppliers,
)
from .shifts import (
    check_opening_shift,
    create_opening_voucher,
    get_opening_dialog_data,
)
from .utilities import (
    get_app_branch,
    get_app_info,
    get_language_options,
    get_pos_profile_tax_inclusive,
    get_selling_price_lists,
    get_translation_dict,
    get_version,
)
from .utils import get_active_pos_profile, get_default_warehouse
