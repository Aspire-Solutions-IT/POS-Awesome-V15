import importlib.util
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


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
    frappe_module.attach_print = lambda *args, **kwargs: None
    frappe_module.sendmail = lambda *args, **kwargs: None
    frappe_module.get_traceback = lambda: "traceback"
    frappe_module.log_error = lambda *args, **kwargs: None
    frappe_module.logger = lambda *args, **kwargs: SimpleNamespace(info=lambda *a, **k: None)
    frappe_module.flags = SimpleNamespace(ignore_account_permission=False)
    frappe_module.db = types.SimpleNamespace(
        exists=lambda *args, **kwargs: False,
        get_value=lambda *args, **kwargs: None,
    )
    frappe_module.conf = {}
    frappe_module.local = SimpleNamespace(conf={}, site="")

    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.cint = lambda value=0: int(value or 0)
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
        self.company = "Test Company"
        self.customer = "Test Customer"
        self.currency = "GBP"
        self.rounded_total = grand_total
        self.grand_total = grand_total
        self.docstatus = 0
        self.flags = SimpleNamespace(ignore_permissions=False)

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


class TestSalesOrderSubmit(TestCase):
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

        self.assertEqual(result, {"name": "SO-TEST-0001", "status": 1})
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

        self.assertEqual(result, {"name": "SO-TEST-0001", "status": 1})
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

        self.assertEqual(result, {"name": "SO-TEST-0001", "status": 1})
        self.assertEqual(call_order, ["payments", "delivery_note"])
        create_payment_entries.assert_called_once_with(so_doc, order["payments"])
        auto_dn.assert_called_once_with(so_doc)
        self.assertFalse(enqueue.called)
