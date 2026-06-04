import importlib.util
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

    frappe_module = types.ModuleType("frappe")
    frappe_module._ = lambda value: value
    frappe_module.whitelist = _whitelist
    frappe_module.enqueue = lambda *args, **kwargs: None
    frappe_module.get_cached_doc = lambda *args, **kwargs: SimpleNamespace()
    frappe_module.get_doc = lambda *args, **kwargs: None
    frappe_module.attach_print = lambda *args, **kwargs: None
    frappe_module.sendmail = lambda *args, **kwargs: None
    frappe_module.get_traceback = lambda: "traceback"
    frappe_module.log_error = lambda *args, **kwargs: None
    frappe_module.db = types.SimpleNamespace(get_value=lambda *args, **kwargs: None)
    frappe_module.conf = {}
    frappe_module.local = SimpleNamespace(conf={}, site="")

    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.cint = lambda value=0: int(value or 0)
    frappe_utils.flt = lambda value=0, *args, **kwargs: float(value or 0)
    frappe_utils.getdate = lambda value: value
    frappe_utils.nowdate = lambda: "2026-06-03"

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


class TestSalesOrderReceiptEmail(TestCase):
    def test_on_submit_enqueues_receipt_email_for_eligible_pos_order(self):
        doc = SimpleNamespace(name="SO-0001", pos_profile="POS-1")

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt")
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="customer@example.com"
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.on_submit(doc, None)

        enqueue.assert_called_once_with(
            "posawesome.posawesome.api.sales_orders._send_receipt_email_job",
            queue="short",
            enqueue_after_commit=True,
            sales_order_name="SO-0001",
            recipient="customer@example.com",
            pos_profile="POS-1",
            print_format="POS Receipt",
        )

    def test_on_submit_skips_when_customer_email_is_missing(self):
        doc = SimpleNamespace(name="SO-0002", pos_profile="POS-1")

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt")
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value=""
        ), patch.object(
            sales_orders, "_log_receipt_skip"
        ) as log_skip, patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.on_submit(doc, None)

        enqueue.assert_not_called()
        log_skip.assert_called_once_with(doc, "Customer email is missing.")

    def test_on_submit_skips_send_for_local_or_dev_site(self):
        doc = SimpleNamespace(name="SO-0002A", pos_profile="POS-1")

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt")
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="customer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=True
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.on_submit(doc, None)

        enqueue.assert_not_called()

    def test_on_submit_enqueues_when_not_local_or_dev_site(self):
        doc = SimpleNamespace(name="SO-0002B", pos_profile="POS-1")

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt")
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="customer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.on_submit(doc, None)

        enqueue.assert_called_once()

    def test_should_auto_email_receipt_requires_pos_order(self):
        doc = SimpleNamespace(name="SO-0003", is_pos=0, pos_profile="POS-1")

        should_send, print_format = sales_orders._should_auto_email_receipt(doc)

        self.assertFalse(should_send)
        self.assertEqual(print_format, "")

    def test_should_auto_email_receipt_logs_when_print_format_missing(self):
        doc = SimpleNamespace(name="SO-0004", is_pos=1, pos_profile="POS-1")

        with patch.object(
            sales_orders, "_get_receipt_email_settings", return_value=(1, "")
        ), patch.object(sales_orders, "_log_receipt_skip") as log_skip:
            should_send, print_format = sales_orders._should_auto_email_receipt(doc, log_skip=True)

        self.assertFalse(should_send)
        self.assertEqual(print_format, "")
        log_skip.assert_called_once_with(
            doc, "Receipt email is enabled but no print format is configured."
        )

    def test_is_dev_or_local_environment_uses_local_site_name(self):
        with patch.object(sales_orders.frappe, "conf", {}), patch.object(
            sales_orders.frappe, "local", SimpleNamespace(conf={}, site="agile.localhost")
        ):
            self.assertTrue(sales_orders._is_dev_or_local_environment())

    def test_resolve_customer_email_prefers_billing_address_email(self):
        doc = SimpleNamespace(
            customer="CUST-0001",
            customer_address="BILL-ADDR",
            shipping_address_name="SHIP-ADDR",
        )

        with patch.object(
            sales_orders, "_get_address_email", side_effect=["billing@example.com", "shipping@example.com"]
        ), patch.object(sales_orders.frappe.db, "get_value") as get_value:
            email = sales_orders._resolve_customer_email(doc)

        self.assertEqual(email, "billing@example.com")
        get_value.assert_not_called()

    def test_resolve_customer_email_falls_back_to_shipping_then_customer(self):
        doc = SimpleNamespace(
            customer="CUST-0002",
            customer_address="BILL-ADDR",
            shipping_address_name="SHIP-ADDR",
        )

        with patch.object(
            sales_orders, "_get_address_email", side_effect=["", "shipping@example.com"]
        ), patch.object(sales_orders.frappe.db, "get_value") as get_value:
            email = sales_orders._resolve_customer_email(doc)

        self.assertEqual(email, "shipping@example.com")
        get_value.assert_not_called()

    def test_resolve_customer_email_falls_back_to_customer_record_last(self):
        doc = SimpleNamespace(
            customer="CUST-0003",
            customer_address="BILL-ADDR",
            shipping_address_name="SHIP-ADDR",
        )

        with patch.object(sales_orders, "_get_address_email", side_effect=["", ""]), patch.object(
            sales_orders.frappe.db, "get_value", return_value="customer@example.com"
        ) as get_value:
            email = sales_orders._resolve_customer_email(doc)

        self.assertEqual(email, "customer@example.com")
        get_value.assert_called_once_with("Customer", "CUST-0003", "email_id")

    def test_send_receipt_email_job_sends_attachment_email(self):
        doc = SimpleNamespace(name="SO-0005", doctype="Sales Order", is_pos=1, pos_profile="POS-1")
        attachment = {"fname": "SO-0005.pdf", "fcontent": b"pdf"}

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders.frappe, "attach_print", return_value=attachment
        ) as attach_print, patch.object(
            sales_orders.frappe, "sendmail"
        ) as sendmail:
            sales_orders._send_receipt_email_job(
                "SO-0005",
                "customer@example.com",
                "POS-1",
                "POS Receipt",
            )

        attach_print.assert_called_once_with(
            doctype="Sales Order",
            name="SO-0005",
            print_format="POS Receipt",
            doc=doc,
        )
        sendmail.assert_called_once_with(
            recipients=["customer@example.com"],
            subject="Receipt for Sales Order SO-0005",
            message="Please find your receipt attached.",
            attachments=[attachment],
            reference_doctype="Sales Order",
            reference_name="SO-0005",
        )

    def test_send_receipt_email_job_logs_errors(self):
        with patch.object(
            sales_orders.frappe, "get_doc", side_effect=RuntimeError("boom")
        ), patch.object(
            sales_orders.frappe, "get_traceback", return_value="traceback"
        ), patch.object(
            sales_orders.frappe, "log_error"
        ) as log_error:
            sales_orders._send_receipt_email_job(
                "SO-0006",
                "customer@example.com",
                "POS-1",
                "POS Receipt",
            )

        log_error.assert_called_once_with(
            "traceback", "POSAwesome Receipt Email Error - Sales Order SO-0006"
        )
