import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch


def _install_stub_modules():
    def _whitelist(fn=None, **_kwargs):
        if fn is None:
            return lambda wrapped: wrapped
        return fn

    def _throw(message):
        raise RuntimeError(message)

    frappe_module = types.ModuleType("frappe")
    frappe_module._ = lambda value: value
    frappe_module.whitelist = _whitelist
    frappe_module.throw = _throw
    frappe_module.enqueue = lambda *args, **kwargs: None
    frappe_module.get_cached_doc = lambda *args, **kwargs: SimpleNamespace()
    frappe_module.get_doc = lambda *args, **kwargs: None
    frappe_module.get_all = lambda *args, **kwargs: []
    frappe_module.get_list = lambda *args, **kwargs: []
    frappe_module.attach_print = lambda *args, **kwargs: None
    frappe_module.sendmail = lambda *args, **kwargs: None
    frappe_module.get_traceback = lambda: "traceback"
    frappe_module.log_error = lambda *args, **kwargs: None
    frappe_module.logger = lambda *args, **kwargs: SimpleNamespace(info=lambda *a, **k: None)
    frappe_module.flags = SimpleNamespace(ignore_account_permission=False)
    frappe_module.db = types.SimpleNamespace(
        exists=lambda *args, **kwargs: False,
        get_value=lambda *args, **kwargs: None,
        has_column=lambda *args, **kwargs: True,
    )
    frappe_module.conf = {}
    frappe_module.local = SimpleNamespace(conf={}, site="")

    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.cint = lambda value=0: int(value or 0)
    frappe_utils.cstr = lambda value="": "" if value is None else str(value)
    frappe_utils.flt = lambda value=0, precision=None, *args, **kwargs: round(float(value or 0), precision) if precision is not None else float(value or 0)
    frappe_utils.getdate = lambda value: value
    frappe_utils.nowdate = lambda: "2026-06-15"

    erpnext_accounts_party = types.ModuleType("erpnext.accounts.party")
    erpnext_accounts_party.get_party_account = lambda *args, **kwargs: None

    erpnext_sales_order = types.ModuleType("erpnext.selling.doctype.sales_order.sales_order")
    erpnext_sales_order.make_delivery_note = lambda *args, **kwargs: None
    erpnext_sales_order.make_sales_invoice = lambda *args, **kwargs: None

    payment_entry_module = types.ModuleType("posawesome.posawesome.api.payment_entry")
    payment_entry_module.create_payment_entry = lambda *args, **kwargs: None

    update_child_qty_rate_module = types.ModuleType("customer_due_dates.api.update_child_qty_rate")
    update_child_qty_rate_module.update_child_qty_rate = lambda *args, **kwargs: None

    package_roots = {
        "posawesome": Path(__file__).resolve().parents[3],
        "posawesome.posawesome": Path(__file__).resolve().parents[2],
        "posawesome.posawesome.api": Path(__file__).resolve().parents[1],
    }

    for name, path in package_roots.items():
        module = types.ModuleType(name)
        module.__path__ = [str(path)]
        sys.modules[name] = module

    sys.modules["frappe"] = frappe_module
    sys.modules["frappe.utils"] = frappe_utils
    sys.modules["erpnext.accounts.party"] = erpnext_accounts_party
    sys.modules["erpnext.selling.doctype.sales_order.sales_order"] = erpnext_sales_order
    sys.modules["posawesome.posawesome.api.payment_entry"] = payment_entry_module
    sys.modules["customer_due_dates"] = types.ModuleType("customer_due_dates")
    sys.modules["customer_due_dates.api"] = types.ModuleType("customer_due_dates.api")
    sys.modules["customer_due_dates.api.update_child_qty_rate"] = update_child_qty_rate_module


def _load_sales_orders_module():
    _install_stub_modules()
    module_name = "posawesome.posawesome.api.sales_orders"
    module_path = Path(__file__).resolve().with_name("sales_orders.py")
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


sales_orders = _load_sales_orders_module()


class FakeSalesOrder:
    def __init__(self, grand_total=300):
        self.name = "SO-TEST-0001"
        self.doctype = "Sales Order"
        self.company = "Test Company"
        self.customer = "Test Customer"
        self.currency = "GBP"
        self.rounded_total = grand_total
        self.grand_total = grand_total
        self.docstatus = 0
        self.flags = SimpleNamespace(ignore_permissions=False)
        self.tags = []

    def update(self, values):
        for key, value in values.items():
            setattr(self, key, value)

    def save(self):
        self.saved = True

    def submit(self):
        self.docstatus = 1
        self.submitted = True

    def precision(self, _fieldname):
        return 2

    def get(self, fieldname, default=None):
        return getattr(self, fieldname, default)

    def add_tag(self, tag):
        self.tags.append(tag)


class FakeGroupedSalesOrder(FakeSalesOrder):
    def __init__(self, name, grand_total=100):
        super().__init__(grand_total=grand_total)
        self.name = name


class TestSalesOrderSubmit(TestCase):
    def test_get_managed_sales_orders_applies_rfs_and_customer_filters(self):
        captured = {}

        def fake_get_list(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return []

        with patch.object(sales_orders.frappe, "get_list", side_effect=fake_get_list):
            result = sales_orders.get_managed_sales_orders("Test Company", "GBP", "SO-TEST")

        self.assertEqual(result, [])
        self.assertEqual(captured["args"][0], "Sales Order")
        self.assertEqual(captured["kwargs"]["filters"]["rfs_order"], 1)
        self.assertEqual(captured["kwargs"]["filters"]["customer"], ["not in", ["13682"]])
        self.assertEqual(captured["kwargs"]["filters"]["name"], ["like", "%SO-TEST%"])

    def test_get_managed_sales_order_returns_component_due_date_context(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-1",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            customer_name="RFS Customer",
            status="On Hold",
            transaction_date="2026-07-23",
            delivery_date="2026-07-30",
            prefered_earliest_delivery_date="2026-08-15",
            customer_ref="CUST-REF",
            customer_order_ref="ORD-REF",
            posa_notes="Handle carefully",
            shopify_notes="Handle carefully",
            auto_release_date="2026-08-10",
            shipping_address_name="ADDR-1",
            customer_address="ADDR-2",
            currency="GBP",
            grand_total=100,
            rounded_total=100,
            modified="2026-07-23 10:00:00",
            owner="test@example.com",
            items=[
                SimpleNamespace(
                    name="SOI-1",
                    item_code="ITEM-1",
                    item_name="Item 1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=0,
                    delivered_qty=0,
                    rate=100,
                    amount=100,
                    delivery_date="2026-07-30",
                    component_due_date="2026-08-01",
                    quoted_date="2026-07-28",
                    posa_notes=None,
                ),
                SimpleNamespace(
                    name="SOI-2",
                    item_code="ITEM-2",
                    item_name="Item 2",
                    description="Desc 2",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=2,
                    picked_qty=0,
                    delivered_qty=0,
                    rate=50,
                    amount=100,
                    delivery_date="2026-08-02",
                    component_due_date="2026-08-11",
                    quoted_date="2026-07-29",
                    posa_notes=None,
                ),
            ],
        )

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc):
            result = sales_orders.get_managed_sales_order("SO-MANAGED-1")

        self.assertEqual(result["name"], "SO-MANAGED-1")
        self.assertEqual(result["latest_component_due_date"], "2026-08-11")
        self.assertEqual(len(result["items"]), 2)
        self.assertEqual(result["items"][0]["component_due_date"], "2026-08-01")
        self.assertFalse(result["items"][0]["is_locked"])

    def test_get_managed_sales_order_marks_picked_items_locked(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-LOCK-1",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            customer_name="RFS Customer",
            status="To Deliver",
            transaction_date="2026-07-23",
            delivery_date="2026-07-30",
            prefered_earliest_delivery_date="2026-08-15",
            customer_ref=None,
            customer_order_ref=None,
            posa_notes=None,
            shopify_notes=None,
            auto_release_date=None,
            shipping_address_name=None,
            customer_address=None,
            currency="GBP",
            grand_total=100,
            rounded_total=100,
            modified="2026-07-23 10:00:00",
            owner="test@example.com",
            items=[
                SimpleNamespace(
                    name="SOI-PICKED",
                    item_code="ITEM-1",
                    item_name="Item 1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=1,
                    delivered_qty=0,
                    rate=100,
                    amount=100,
                    delivery_date="2026-07-30",
                    component_due_date=None,
                    quoted_date=None,
                    posa_notes=None,
                ),
            ],
        )

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc):
            result = sales_orders.get_managed_sales_order("SO-MANAGED-LOCK-1")

        self.assertTrue(result["items"][0]["is_locked"])
        self.assertEqual(result["items"][0]["lock_reason"], "Picked qty is greater than 0.")

    def test_get_managed_sales_order_marks_delivered_items_locked(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-LOCK-2",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            customer_name="RFS Customer",
            status="To Deliver",
            transaction_date="2026-07-23",
            delivery_date="2026-07-30",
            prefered_earliest_delivery_date="2026-08-15",
            customer_ref=None,
            customer_order_ref=None,
            posa_notes=None,
            shopify_notes=None,
            auto_release_date=None,
            shipping_address_name=None,
            customer_address=None,
            currency="GBP",
            grand_total=100,
            rounded_total=100,
            modified="2026-07-23 10:00:00",
            owner="test@example.com",
            items=[
                SimpleNamespace(
                    name="SOI-DELIVERED",
                    item_code="ITEM-1",
                    item_name="Item 1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=0,
                    delivered_qty=1,
                    rate=100,
                    amount=100,
                    delivery_date="2026-07-30",
                    component_due_date=None,
                    quoted_date=None,
                    posa_notes=None,
                ),
            ],
        )

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc):
            result = sales_orders.get_managed_sales_order("SO-MANAGED-LOCK-2")

        self.assertTrue(result["items"][0]["is_locked"])
        self.assertEqual(result["items"][0]["lock_reason"], "Delivered qty is greater than 0.")

    def test_get_managed_sales_order_marks_draft_pick_lists_locked(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-LOCK-3",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            customer_name="RFS Customer",
            status="To Deliver",
            transaction_date="2026-07-23",
            delivery_date="2026-07-30",
            prefered_earliest_delivery_date="2026-08-15",
            customer_ref=None,
            customer_order_ref=None,
            posa_notes=None,
            shopify_notes=None,
            auto_release_date=None,
            shipping_address_name=None,
            customer_address=None,
            currency="GBP",
            grand_total=100,
            rounded_total=100,
            modified="2026-07-23 10:00:00",
            owner="test@example.com",
            items=[
                SimpleNamespace(
                    name="SOI-DRAFT-PL",
                    item_code="ITEM-1",
                    item_name="Item 1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=0,
                    delivered_qty=0,
                    rate=100,
                    amount=100,
                    delivery_date="2026-07-30",
                    component_due_date=None,
                    quoted_date=None,
                    posa_notes=None,
                ),
            ],
        )

        def fake_get_all(doctype, **kwargs):
            if doctype == "Pick List Item":
                return [{"parent": "PL-DRAFT-1", "sales_order_item": "SOI-DRAFT-PL"}]
            if doctype == "Pick List":
                return [{"name": "PL-DRAFT-1", "status": "Draft", "docstatus": 0, "per_delivered": 0}]
            return []

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders.frappe, "get_all", side_effect=fake_get_all
        ):
            result = sales_orders.get_managed_sales_order("SO-MANAGED-LOCK-3")

        self.assertTrue(result["items"][0]["is_locked"])
        self.assertEqual(result["items"][0]["linked_pick_lists"][0]["status"], "Draft")
        self.assertIn("PL-DRAFT-1 (Draft)", result["items"][0]["lock_reason"])

    def test_update_managed_sales_order_updates_allowed_fields_only(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-2",
            docstatus=1,
            rfs_order=1,
            customer="RFS-002",
            customer_ref=None,
            prefered_earliest_delivery_date=None,
            posa_notes=None,
            shopify_notes=None,
            flags=SimpleNamespace(),
            save=MagicMock(),
            reload=lambda: None,
        )

        payload = {
            "name": "SO-MANAGED-2",
            "customer_ref": "NEW-REF",
            "prefered_earliest_delivery_date": "2026-08-20",
            "posa_notes": "Updated note",
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-MANAGED-2"}
        ):
            result = sales_orders.update_managed_sales_order(payload)

        self.assertEqual(result["name"], "SO-MANAGED-2")
        self.assertEqual(so_doc.customer_ref, "NEW-REF")
        self.assertEqual(so_doc.prefered_earliest_delivery_date, "2026-08-20")
        self.assertEqual(so_doc.posa_notes, "Updated note")
        self.assertEqual(so_doc.shopify_notes, "Updated note")
        self.assertTrue(so_doc.flags.ignore_permissions)
        self.assertTrue(so_doc.flags.ignore_validate_update_after_submit)
        so_doc.save.assert_called_once_with(ignore_permissions=True)

    def test_update_managed_sales_order_items_reuses_sales_order_update_path(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-ITEMS-1",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            customer_name="RFS Customer",
            status="To Deliver",
            transaction_date="2026-07-23",
            delivery_date="2026-07-30",
            prefered_earliest_delivery_date="2026-08-15",
            customer_ref=None,
            customer_order_ref=None,
            posa_notes=None,
            shopify_notes=None,
            auto_release_date=None,
            shipping_address_name=None,
            customer_address=None,
            currency="GBP",
            grand_total=100,
            rounded_total=100,
            modified="2026-07-23 10:00:00",
            owner="test@example.com",
            reload=MagicMock(),
            items=[
                SimpleNamespace(
                    name="SOI-EDITABLE",
                    item_code="ITEM-1",
                    item_name="Item 1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=0,
                    delivered_qty=0,
                    rate=100,
                    amount=100,
                    delivery_date="2026-07-30",
                    component_due_date=None,
                    quoted_date=None,
                    posa_notes=None,
                    bom_no=None,
                    conversion_factor=1,
                ),
            ],
        )

        payload = {
            "name": "SO-MANAGED-ITEMS-1",
            "items": [
                {
                    "docname": "SOI-EDITABLE",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 2,
                    "conversion_factor": 1,
                }
            ],
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-MANAGED-ITEMS-1"}
        ), patch(
            "customer_due_dates.api.update_child_qty_rate.update_child_qty_rate"
        ) as update_items:
            result = sales_orders.update_managed_sales_order_items(payload)

        self.assertEqual(result["name"], "SO-MANAGED-ITEMS-1")
        update_items.assert_called_once()
        call_kwargs = update_items.call_args.kwargs
        self.assertEqual(call_kwargs["parent_doctype"], "Sales Order")
        self.assertEqual(call_kwargs["parent_doctype_name"], "SO-MANAGED-ITEMS-1")
        self.assertIn("\"qty\": 2.0", call_kwargs["trans_items"])
        self.assertIn("\"rate\": 100.0", call_kwargs["trans_items"])
        self.assertIn("\"warehouse\": \"Main - TC\"", call_kwargs["trans_items"])
        self.assertIn("\"delivery_date\": \"2026-07-30\"", call_kwargs["trans_items"])

    def test_update_managed_sales_order_items_blocks_picked_rows(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-ITEMS-2",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            items=[
                SimpleNamespace(
                    name="SOI-PICKED",
                    item_code="ITEM-1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=1,
                    delivered_qty=0,
                    rate=100,
                    delivery_date="2026-07-30",
                    bom_no=None,
                    conversion_factor=1,
                ),
            ],
        )

        payload = {
            "name": "SO-MANAGED-ITEMS-2",
            "items": [
                {
                    "docname": "SOI-PICKED",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 2,
                    "conversion_factor": 1,
                }
            ],
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc):
            with self.assertRaisesRegex(RuntimeError, "Picked qty is greater than 0"):
                sales_orders.update_managed_sales_order_items(payload)

    def test_update_managed_sales_order_items_blocks_delivered_rows(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-ITEMS-3",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            items=[
                SimpleNamespace(
                    name="SOI-DELIVERED",
                    item_code="ITEM-1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=0,
                    delivered_qty=1,
                    rate=100,
                    delivery_date="2026-07-30",
                    bom_no=None,
                    conversion_factor=1,
                ),
            ],
        )

        payload = {
            "name": "SO-MANAGED-ITEMS-3",
            "items": [
                {
                    "docname": "SOI-DELIVERED",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 2,
                    "conversion_factor": 1,
                }
            ],
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc):
            with self.assertRaisesRegex(RuntimeError, "Delivered qty is greater than 0"):
                sales_orders.update_managed_sales_order_items(payload)

    def test_update_managed_sales_order_items_blocks_active_pick_lists(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-ITEMS-4",
            docstatus=1,
            rfs_order=1,
            customer="RFS-001",
            items=[
                SimpleNamespace(
                    name="SOI-PL",
                    item_code="ITEM-1",
                    description="Desc 1",
                    warehouse="Main - TC",
                    uom="Nos",
                    qty=1,
                    picked_qty=0,
                    delivered_qty=0,
                    rate=100,
                    delivery_date="2026-07-30",
                    bom_no=None,
                    conversion_factor=1,
                ),
            ],
        )

        payload = {
            "name": "SO-MANAGED-ITEMS-4",
            "items": [
                {
                    "docname": "SOI-PL",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 2,
                    "conversion_factor": 1,
                }
            ],
        }

        def fake_get_all(doctype, **kwargs):
            if doctype == "Pick List Item":
                return [{"parent": "PL-OPEN-1", "sales_order_item": "SOI-PL"}]
            if doctype == "Pick List":
                return [{"name": "PL-OPEN-1", "status": "Open", "docstatus": 1, "per_delivered": 0}]
            return []

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders.frappe, "get_all", side_effect=fake_get_all
        ):
            with self.assertRaisesRegex(RuntimeError, "PL-OPEN-1 \\(Open\\)"):
                sales_orders.update_managed_sales_order_items(payload)

    def test_search_orders_only_requests_rfs_sales_orders(self):
        captured = {}

        def fake_get_list(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return []

        with patch.object(sales_orders.frappe, "get_list", side_effect=fake_get_list):
            result = sales_orders.search_orders("Test Company", "GBP", "SO-")

        self.assertEqual(result, [])
        self.assertEqual(captured["args"][0], "Sales Order")
        self.assertEqual(captured["kwargs"]["filters"]["rfs_order"], 1)
        self.assertEqual(captured["kwargs"]["filters"]["company"], "Test Company")
        self.assertEqual(captured["kwargs"]["filters"]["currency"], "GBP")
        self.assertEqual(captured["kwargs"]["filters"]["name"], ["like", "%SO-%"])

    def test_get_unique_order_ref_skips_existing_sales_order_refs(self):
        seen_candidates = iter(["ORALREADYUSED", "ORFRESHREF01"])

        with patch.object(sales_orders, "_generate_order_ref", side_effect=lambda: next(seen_candidates)), patch.object(
            sales_orders.frappe,
            "get_all",
            side_effect=lambda *args, **kwargs: ["SO-0001"]
            if kwargs.get("filters", {}).get("customer_order_ref") == "ORALREADYUSED"
            else [],
        ):
            result = sales_orders.get_unique_order_ref()

        self.assertEqual(result, "ORFRESHREF01")

    def test_map_delivery_dates_normalizes_preferred_earliest_delivery_date(self):
        order = {
            "preferred_earliest_delivery_date": "2026-07-30",
            "items": [],
        }

        sales_orders._map_delivery_dates(order)

        self.assertEqual(order["prefered_earliest_delivery_date"], "2026-07-30")
        self.assertEqual(order["preferred_earliest_delivery_date"], "2026-07-30")

    def test_create_payment_entries_falls_back_to_sales_order_name_for_reference_no(self):
        so_doc = FakeSalesOrder(grand_total=300)
        so_doc.posa_pos_opening_shift = None
        so_doc.posa_authorization_code = None

        created_entries = []

        class FakePaymentEntry:
            def __init__(self):
                self.references = []
                self.flags = SimpleNamespace(ignore_permissions=False)

            def append(self, fieldname, value):
                if fieldname == "references":
                    self.references.append(value)

            def save(self):
                self.saved = True

            def submit(self):
                self.submitted = True

        def fake_create_payment_entry(**kwargs):
            created_entries.append(kwargs)
            return FakePaymentEntry()

        with patch.object(sales_orders, "create_payment_entry", side_effect=fake_create_payment_entry):
            sales_orders._create_payment_entries(
                so_doc,
                [{"mode_of_payment": "Bank", "amount": 100}],
            )

        self.assertEqual(created_entries[0]["reference_no"], "SO-TEST-0001")
        self.assertEqual(created_entries[0]["reference_date"], "2026-06-15")

    def test_submit_sales_order_blocks_zero_payment(self):
        so_doc = FakeSalesOrder()
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 0}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            with self.assertRaisesRegex(RuntimeError, "Please enter payment amount"):
                sales_orders.submit_sales_order(json.dumps(order), json.dumps({}))

        self.assertEqual(so_doc.docstatus, 0)
        self.assertFalse(enqueue.called)

    def test_submit_sales_order_replaces_duplicate_customer_order_ref(self):
        so_doc = FakeSalesOrder()
        order = {
            "doctype": "Sales Order",
            "customer_order_ref": "ORDUPLICATE1",
            "payments": [{"mode_of_payment": "Cash", "amount": 10}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(
            sales_orders, "_generate_order_ref", return_value="ORUNIQUE0001"
        ), patch.object(
            sales_orders.frappe,
            "get_all",
            side_effect=lambda *args, **kwargs: ["SO-EXISTING"]
            if kwargs.get("filters", {}).get("customer_order_ref") == "ORDUPLICATE1"
            else [],
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ):
            sales_orders.submit_sales_order(json.dumps(order), json.dumps({}))

        self.assertEqual(so_doc.customer_order_ref, "ORUNIQUE0001")

    def test_validate_split_groups_rejects_duplicate_assignment(self):
        order = {
            "items": [
                {"item_code": "A", "posa_row_id": "row-1"},
                {"item_code": "B", "posa_row_id": "row-2"},
            ],
            "posa_split_groups": [
                {"group_id": "g1", "label": "Group 1", "row_ids": ["row-1", "row-2"]},
                {"group_id": "g2", "label": "Group 2", "row_ids": ["row-2"]},
            ],
        }

        with self.assertRaisesRegex(RuntimeError, "assigned to multiple split groups"):
            sales_orders._validate_split_groups(order)

    def test_allocate_group_payments_splits_pro_rata_with_remainder(self):
        allocations = sales_orders._allocate_group_payments(
            [{"mode_of_payment": "Cash", "amount": 100}],
            [
                {"group_id": "g1", "grand_total": 33.33},
                {"group_id": "g2", "grand_total": 66.67},
            ],
            2,
        )

        self.assertEqual(allocations["g1"][0]["amount"], 33.33)
        self.assertEqual(allocations["g2"][0]["amount"], 66.67)

    def test_submit_sales_order_creates_grouped_orders_and_splits_payments(self):
        order = {
            "doctype": "Sales Order",
            "customer_order_ref": "ORBASE1234",
            "rounded_total": 300,
            "grand_total": 300,
            "posa_split_delivery": 1,
            "items": [
                {"item_code": "ITEM-1", "posa_row_id": "row-1", "qty": 1, "rate": 100},
                {"item_code": "ITEM-2", "posa_row_id": "row-2", "qty": 1, "rate": 200},
            ],
            "posa_split_groups": [
                {"group_id": "living", "label": "Living", "row_ids": ["row-1"]},
                {"group_id": "bedroom", "label": "Bedroom", "row_ids": ["row-2"]},
            ],
            "payments": [{"mode_of_payment": "Cash", "amount": 300}],
        }

        created_docs = []

        def fake_save_sales_order_doc(payload):
            name = f"SO-GROUP-{len(created_docs) + 1}"
            grand_total = 100 if len(created_docs) == 0 else 200
            doc = FakeGroupedSalesOrder(name=name, grand_total=grand_total)
            doc.update(payload)
            created_docs.append(doc)
            return doc

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(
            sales_orders, "_save_sales_order_doc_from_payload", side_effect=fake_save_sales_order_doc
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ) as auto_dn, patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue, patch.object(
            sales_orders.frappe,
            "get_all",
            return_value=[],
        ):
            result = sales_orders.submit_sales_order(json.dumps(order), json.dumps({}))

        self.assertEqual(result["name"], "SO-GROUP-1")
        self.assertEqual(result["names"], ["SO-GROUP-1", "SO-GROUP-2"])
        self.assertEqual(result["group_map"], {"living": "SO-GROUP-1", "bedroom": "SO-GROUP-2"})
        self.assertEqual(created_docs[0].must_be_fully_allocated, 1)
        self.assertEqual(created_docs[1].must_be_fully_allocated, 1)
        self.assertEqual(created_docs[0].customer_order_ref, "ORBASE1234-01")
        self.assertEqual(created_docs[1].customer_order_ref, "ORBASE1234-02")
        self.assertEqual(created_docs[0].items[0]["posa_row_id"], "row-1")
        self.assertEqual(created_docs[1].items[0]["posa_row_id"], "row-2")
        auto_dn.assert_any_call(created_docs[0])
        auto_dn.assert_any_call(created_docs[1])
        self.assertEqual(auto_dn.call_count, 2)
        enqueue.assert_any_call(
            "posawesome.posawesome.api.sales_orders._split_payment_entry_job",
            queue="short",
            order_name="SO-GROUP-1",
            payments=[{"mode_of_payment": "Cash", "amount": 100.0}],
        )
        enqueue.assert_any_call(
            "posawesome.posawesome.api.sales_orders._split_payment_entry_job",
            queue="short",
            order_name="SO-GROUP-2",
            payments=[{"mode_of_payment": "Cash", "amount": 200.0}],
        )

    def test_submit_sales_order_forces_full_allocation_for_pos_split_delivery(self):
        order = {
            "customer": "CUST-0001",
            "doctype": "Sales Order",
            "company": "Test Company",
            "pos_profile": "Main POS",
            "posa_split_delivery": 1,
            "must_be_fully_allocated": 0,
            "payments": [{"mode_of_payment": "Cash", "amount": 100}],
            "rounded_total": 100,
            "grand_total": 100,
            "items": [{"item_code": "ITEM-1", "qty": 1, "rate": 100}],
        }

        captured_payloads = []

        class FakeSalesOrder:
            def __init__(self, payload):
                self.payload = payload
                self.name = "SO-POS-SPLIT-0001"
                self.docstatus = 0
                self.doctype = "Sales Order"
                self.flags = SimpleNamespace(ignore_permissions=False)
                self.posa_delivery_charges = payload.get("posa_delivery_charges")
                self.must_be_fully_allocated = payload.get("must_be_fully_allocated", 0)
                self.rounded_total = payload.get("rounded_total", 0)
                self.grand_total = payload.get("grand_total", 0)

            def update(self, values):
                self.payload.update(values)
                self.must_be_fully_allocated = self.payload.get("must_be_fully_allocated", 0)

            def save(self):
                return self

            def submit(self):
                self.docstatus = 1

            def precision(self, _fieldname):
                return 2

        def fake_get_doc(payload_or_doctype, name=None):
            if isinstance(payload_or_doctype, dict):
                captured_payloads.append(dict(payload_or_doctype))
                return FakeSalesOrder(payload_or_doctype)
            raise AssertionError(f"Unexpected get_doc call: {payload_or_doctype}, {name}")

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_apply_collection_flow_tag"
        ), patch.object(
            sales_orders, "_apply_collect_from_store_tag"
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ), patch.object(
            sales_orders.frappe.db, "exists", return_value=False
        ), patch.object(
            sales_orders.frappe, "get_doc", side_effect=fake_get_doc
        ):
            result = sales_orders.submit_sales_order(json.dumps(order), json.dumps({}))

        self.assertEqual(result["name"], "SO-POS-SPLIT-0001")
        self.assertEqual(captured_payloads[0]["must_be_fully_allocated"], 1)

    def test_submit_sales_order_preserves_pending_auto_hold_reason(self):
        order = {
            "customer": "CUST-0001",
            "doctype": "Sales Order",
            "company": "Test Company",
            "pos_profile": "Main POS",
            "posa_pending_auto_hold_reason": "Partial Payment",
            "payments": [{"mode_of_payment": "Cash", "amount": 50}],
            "rounded_total": 100,
            "grand_total": 100,
            "items": [{"item_code": "ITEM-1", "qty": 1, "rate": 100}],
        }

        captured_payloads = []

        class FakeSalesOrder:
            def __init__(self, payload):
                self.payload = payload
                self.name = "SO-HOLD-0001"
                self.docstatus = 0
                self.doctype = "Sales Order"
                self.flags = SimpleNamespace(ignore_permissions=False)
                self.posa_delivery_charges = payload.get("posa_delivery_charges")
                self.must_be_fully_allocated = payload.get("must_be_fully_allocated", 0)
                self.rounded_total = payload.get("rounded_total", 0)
                self.grand_total = payload.get("grand_total", 0)
                self.posa_pending_auto_hold_reason = payload.get("posa_pending_auto_hold_reason", "")

            def update(self, values):
                self.payload.update(values)

            def save(self):
                return self

            def submit(self):
                self.docstatus = 1

            def precision(self, _fieldname):
                return 2

        def fake_get_doc(payload_or_doctype, name=None):
            if isinstance(payload_or_doctype, dict):
                captured_payloads.append(dict(payload_or_doctype))
                return FakeSalesOrder(payload_or_doctype)
            raise AssertionError(f"Unexpected get_doc call: {payload_or_doctype}, {name}")

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_apply_collection_flow_tag"
        ), patch.object(
            sales_orders, "_apply_collect_from_store_tag"
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ), patch.object(
            sales_orders.frappe.db, "exists", return_value=False
        ), patch.object(
            sales_orders.frappe, "get_doc", side_effect=fake_get_doc
        ):
            result = sales_orders.submit_sales_order(json.dumps(order), json.dumps({}))

        self.assertEqual(result["name"], "SO-HOLD-0001")
        self.assertEqual(captured_payloads[0]["posa_pending_auto_hold_reason"], "Partial Payment")

    def test_submit_sales_order_allows_zero_payment_when_explicitly_enabled(self):
        so_doc = FakeSalesOrder()
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 0}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ) as auto_dn, patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            result = sales_orders.submit_sales_order(
                json.dumps(order),
                json.dumps(
                    {
                        "sales_order_settlement_state": "none",
                        "allow_no_payment_order_submit": 1,
                    }
                ),
            )

        self.assertEqual(result, {"name": "SO-TEST-0001", "status": 1, "doctype": "Sales Order"})
        self.assertEqual(so_doc.docstatus, 1)
        auto_dn.assert_called_once_with(so_doc)
        self.assertFalse(enqueue.called)

    def test_submit_sales_order_enqueues_payment_entries_for_deposit(self):
        so_doc = FakeSalesOrder(grand_total=300)
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 100}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ) as auto_dn, patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            result = sales_orders.submit_sales_order(
                json.dumps(order),
                json.dumps({"sales_order_settlement_state": "deposit"}),
            )

        self.assertEqual(result, {"name": "SO-TEST-0001", "status": 1, "doctype": "Sales Order"})
        self.assertEqual(so_doc.docstatus, 1)
        auto_dn.assert_called_once_with(so_doc)
        enqueue.assert_called_once_with(
            "posawesome.posawesome.api.sales_orders._payment_entry_job",
            queue="short",
            order_name="SO-TEST-0001",
            payments=order["payments"],
        )

    def test_submit_sales_order_blocks_deposit_for_collection_delivery_charge(self):
        so_doc = FakeSalesOrder(grand_total=300)
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 100}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_is_collection_delivery_charge_selected", return_value=True
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            with self.assertRaisesRegex(
                RuntimeError,
                "Deposits are not allowed when a collection delivery charge is selected",
            ):
                sales_orders.submit_sales_order(
                    json.dumps(order),
                    json.dumps({"sales_order_settlement_state": "deposit"}),
                )

        self.assertEqual(so_doc.docstatus, 0)
        self.assertFalse(enqueue.called)

    def test_submit_sales_order_accepts_full_payment_without_invoice_creation(self):
        so_doc = FakeSalesOrder(grand_total=300)
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 300}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue, patch.object(
            sales_orders, "make_sales_invoice"
        ) as make_sales_invoice:
            result = sales_orders.submit_sales_order(
                json.dumps(order),
                json.dumps({"sales_order_settlement_state": "full"}),
            )

        self.assertEqual(result, {"name": "SO-TEST-0001", "status": 1, "doctype": "Sales Order"})
        self.assertEqual(so_doc.docstatus, 1)
        self.assertFalse(make_sales_invoice.called)
        enqueue.assert_called_once_with(
            "posawesome.posawesome.api.sales_orders._payment_entry_job",
            queue="short",
            order_name="SO-TEST-0001",
            payments=order["payments"],
        )

    def test_submit_sales_order_creates_collection_full_payment_synchronously_before_dn(self):
        so_doc = FakeSalesOrder(grand_total=300)
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 300}],
        }
        call_order = []

        def track_payments(*args, **kwargs):
            call_order.append("payments")

        def track_delivery_note(*args, **kwargs):
            call_order.append("delivery_note")

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_is_collection_delivery_charge_selected", return_value=True
        ), patch.object(
            sales_orders, "_create_payment_entries", side_effect=track_payments
        ) as create_payment_entries, patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items", side_effect=track_delivery_note
        ) as auto_dn, patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            result = sales_orders.submit_sales_order(
                json.dumps(order),
                json.dumps({"sales_order_settlement_state": "full"}),
            )

        self.assertEqual(result, {"name": "SO-TEST-0001", "status": 1, "doctype": "Sales Order"})
        self.assertEqual(call_order, ["payments", "delivery_note"])
        create_payment_entries.assert_called_once_with(so_doc, order["payments"])
        auto_dn.assert_called_once_with(so_doc)
        self.assertFalse(enqueue.called)

    def test_submit_sales_order_adds_collect_from_store_tag(self):
        so_doc = FakeSalesOrder(grand_total=300)
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 300}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_is_collect_from_store_delivery_charge_selected", return_value=True
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ), patch.object(
            sales_orders, "make_sales_invoice"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ):
            sales_orders.submit_sales_order(
                json.dumps(order),
                json.dumps({"sales_order_settlement_state": "full"}),
            )

        self.assertIn("Collect from Store", so_doc.tags)

    def test_submit_sales_order_adds_taken_on_day_tag_for_collection_flow(self):
        so_doc = FakeSalesOrder(grand_total=300)
        order = {
            "doctype": "Sales Order",
            "payments": [{"mode_of_payment": "Cash", "amount": 300}],
        }

        with patch.object(sales_orders, "_map_delivery_dates"), patch.object(
            sales_orders, "_apply_ns_default_warehouse"
        ), patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_sync_shopify_notes_from_posa"
        ), patch.object(
            sales_orders, "_apply_kit_meta_fields"
        ), patch.object(
            sales_orders, "_apply_delivery_charges_tax_row"
        ), patch.object(
            sales_orders, "_is_collection_delivery_charge_selected", return_value=True
        ), patch.object(
            sales_orders, "_auto_create_delivery_note_for_non_ns_items"
        ), patch.object(
            sales_orders, "make_sales_invoice"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ):
            sales_orders.submit_sales_order(
                json.dumps(order),
                json.dumps({"sales_order_settlement_state": "full"}),
            )

        self.assertIn("Taken on Day", so_doc.tags)
