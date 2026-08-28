import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch


class ValidationError(Exception):
    """Stands in for frappe.ValidationError so throw() can be asserted on."""


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
    def _throw(message, exc=None, **_kwargs):
        raise ValidationError(message)

    frappe_module.throw = _throw
    frappe_module.ValidationError = ValidationError
    frappe_module.get_traceback = lambda: "traceback"
    frappe_module.log_error = lambda *args, **kwargs: None
    frappe_module.logger = lambda *args, **kwargs: SimpleNamespace(info=lambda *a, **k: None)
    frappe_module.db = types.SimpleNamespace(get_value=lambda *args, **kwargs: None)
    frappe_module.conf = {}
    frappe_module.local = SimpleNamespace(conf={}, site="")

    import re as _re

    def _stub_split_emails(txt):
        if not txt:
            return []
        parts = _re.split(r"[,\n;]", str(txt))
        return [part.strip() for part in parts if part.strip()]

    def _stub_validate_email_address(email_str, throw=False):
        emails = _stub_split_emails(email_str)
        valid = [e for e in emails if _re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e)]
        return ", ".join(valid)

    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.cint = lambda value=0: int(value or 0)
    frappe_utils.cstr = lambda value="", *args, **kwargs: "" if value is None else str(value)
    frappe_utils.flt = lambda value=0, *args, **kwargs: float(value or 0)
    frappe_utils.getdate = lambda value: value
    frappe_utils.nowdate = lambda: "2026-06-03"
    frappe_utils.split_emails = _stub_split_emails
    frappe_utils.validate_email_address = _stub_validate_email_address
    frappe_utils_pdf = types.ModuleType("frappe.utils.pdf")
    frappe_utils_pdf.get_pdf = lambda html, options=None, output=None: b"pdf"
    frappe_utils_print_utils = types.ModuleType("frappe.utils.print_utils")
    frappe_utils_print_utils.get_print = lambda *args, **kwargs: "<div>print</div>"

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
    sys.modules["frappe.utils.pdf"] = frappe_utils_pdf
    sys.modules["frappe.utils.print_utils"] = frappe_utils_print_utils
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
            sales_orders,
            "_should_auto_email_receipt",
            return_value=(True, "POS Receipt", ["cc@example.com"]),
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
            cc=["cc@example.com"],
            revised=False,
        )

    def test_on_submit_skips_when_customer_email_is_missing(self):
        doc = SimpleNamespace(name="SO-0002", pos_profile="POS-1")

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt", [])
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
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt", [])
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
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt", [])
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="customer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.on_submit(doc, None)

        enqueue.assert_called_once()

    def test_on_submit_skips_duplicate_queue_when_hook_runs_twice(self):
        doc = SimpleNamespace(name="SO-0002C", pos_profile="POS-1")

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt", [])
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="customer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.on_submit(doc, None)
            sales_orders.on_submit(doc, None)

        enqueue.assert_called_once()

    def test_should_auto_email_receipt_requires_pos_order(self):
        doc = SimpleNamespace(name="SO-0003", is_pos=0, pos_profile="POS-1")

        should_send, print_format, cc_emails = sales_orders._should_auto_email_receipt(doc)

        self.assertFalse(should_send)
        self.assertEqual(print_format, "")
        self.assertEqual(cc_emails, [])

    def test_should_auto_email_receipt_logs_when_print_format_missing(self):
        doc = SimpleNamespace(name="SO-0004", is_pos=1, pos_profile="POS-1")

        with patch.object(
            sales_orders, "_get_receipt_email_settings", return_value=(1, "", [])
        ), patch.object(sales_orders, "_log_receipt_skip") as log_skip:
            should_send, print_format, cc_emails = sales_orders._should_auto_email_receipt(
                doc, log_skip=True
            )

        self.assertFalse(should_send)
        self.assertEqual(print_format, "")
        self.assertEqual(cc_emails, [])
        log_skip.assert_called_once_with(
            doc, "Receipt email is enabled but no print format is configured."
        )

    def test_should_auto_email_receipt_returns_cc_emails_when_eligible(self):
        doc = SimpleNamespace(name="SO-0004A", is_pos=1, pos_profile="POS-1")

        with patch.object(
            sales_orders,
            "_get_receipt_email_settings",
            return_value=(1, "POS Receipt", ["cc@example.com"]),
        ):
            should_send, print_format, cc_emails = sales_orders._should_auto_email_receipt(doc)

        self.assertTrue(should_send)
        self.assertEqual(print_format, "POS Receipt")
        self.assertEqual(cc_emails, ["cc@example.com"])

    def test_parse_cc_emails_splits_and_filters_invalid_addresses(self):
        cc_emails = sales_orders._parse_cc_emails("a@example.com, not-an-email\nb@example.com")

        self.assertEqual(cc_emails, ["a@example.com", "b@example.com"])

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
            sales_orders, "_build_receipt_attachment", return_value=attachment
        ) as build_attachment, patch.object(
            sales_orders, "_get_receipt_sender", return_value="erp@example.com"
        ), patch.object(
            sales_orders.frappe, "sendmail"
        ) as sendmail:
            sales_orders._send_receipt_email_job(
                "SO-0005",
                "customer@example.com",
                "POS-1",
                "POS Receipt",
            )

        build_attachment.assert_called_once_with(doc, "POS Receipt")
        sendmail.assert_called_once_with(
            recipients=["customer@example.com"],
            sender="erp@example.com",
            subject="Your Receipt for Order - SO-0005 - The Furniture Warehouse",
            message="Please find your receipt attached.",
            attachments=[attachment],
            reference_doctype="Sales Order",
            reference_name="SO-0005",
        )

    def test_send_receipt_email_job_includes_cc_when_provided(self):
        doc = SimpleNamespace(name="SO-0005A", doctype="Sales Order", is_pos=1, pos_profile="POS-1")
        attachment = {"fname": "SO-0005A.pdf", "fcontent": b"pdf"}

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_build_receipt_attachment", return_value=attachment
        ), patch.object(
            sales_orders, "_get_receipt_sender", return_value="erp@example.com"
        ), patch.object(
            sales_orders.frappe, "sendmail"
        ) as sendmail:
            sales_orders._send_receipt_email_job(
                "SO-0005A",
                "customer@example.com",
                "POS-1",
                "POS Receipt",
                cc=["cc1@example.com", "cc2@example.com"],
            )

        sendmail.assert_called_once_with(
            recipients=["customer@example.com"],
            sender="erp@example.com",
            subject="Your Receipt for Order - SO-0005A - The Furniture Warehouse",
            message="Please find your receipt attached.",
            attachments=[attachment],
            reference_doctype="Sales Order",
            reference_name="SO-0005A",
            bcc=["cc1@example.com", "cc2@example.com"],
        )

    def test_send_receipt_email_job_falls_back_to_profile_cc_when_none_passed(self):
        doc = SimpleNamespace(name="SO-0005B", doctype="Sales Order", is_pos=1, pos_profile="POS-1")
        attachment = {"fname": "SO-0005B.pdf", "fcontent": b"pdf"}

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_build_receipt_attachment", return_value=attachment
        ), patch.object(
            sales_orders, "_get_receipt_sender", return_value="erp@example.com"
        ), patch.object(
            sales_orders,
            "_get_receipt_email_settings",
            return_value=(1, "POS Receipt", ["profile-cc@example.com"]),
        ), patch.object(
            sales_orders.frappe, "sendmail"
        ) as sendmail:
            sales_orders._send_receipt_email_job(
                "SO-0005B",
                "customer@example.com",
                pos_profile="POS-1",
                print_format=None,
            )

        sendmail.assert_called_once_with(
            recipients=["customer@example.com"],
            sender="erp@example.com",
            subject="Your Receipt for Order - SO-0005B - The Furniture Warehouse",
            message="Please find your receipt attached.",
            attachments=[attachment],
            reference_doctype="Sales Order",
            reference_name="SO-0005B",
            bcc=["profile-cc@example.com"],
        )

    def test_build_receipt_attachment_uses_attach_print_without_override(self):
        doc = SimpleNamespace(name="SO-0005", doctype="Sales Order")
        attachment = {"fname": "SO-0005.pdf", "fcontent": b"pdf"}

        with patch.object(
            sales_orders, "_get_print_format_override", return_value=None
        ), patch.object(sales_orders.frappe, "attach_print", return_value=attachment) as attach_print:
            result = sales_orders._build_receipt_attachment(doc, "POS Receipt")

        self.assertEqual(result, attachment)
        attach_print.assert_called_once_with(
            doctype="Sales Order",
            name="SO-0005",
            print_format="POS Receipt",
            doc=doc,
        )

    def test_build_receipt_attachment_applies_custom_page_size_override(self):
        doc = SimpleNamespace(name="SO 0005/1", doctype="Sales Order")

        with patch.object(
            sales_orders, "_get_print_format_override", return_value={"height": 29.7, "width": 21.0}
        ), patch("frappe.utils.print_utils.get_print", return_value="<div>Receipt</div>") as get_print, patch(
            "frappe.utils.pdf.get_pdf", return_value=b"custom-pdf"
        ) as get_pdf:
            result = sales_orders._build_receipt_attachment(doc, "POS Receipt")

        self.assertEqual(result, {"fname": "SO0005-1.pdf", "fcontent": b"custom-pdf"})
        get_print.assert_called_once_with(
            doctype="Sales Order",
            name="SO 0005/1",
            print_format="POS Receipt",
            doc=doc,
        )
        get_pdf.assert_called_once()
        self.assertIn("page-height: 29.7cm; page-width: 21.0cm;", get_pdf.call_args.args[0])
        self.assertIn("<div>Receipt</div>", get_pdf.call_args.args[0])

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


class TestManagedSalesOrderReceiptResend(TestCase):
    def _order(self, **overrides):
        defaults = dict(
            doctype="Sales Order",
            name="SO-9001",
            customer="CUST-1",
            pos_profile="POS-1",
            customer_address="ADDR-BILL",
            shipping_address_name="ADDR-SHIP",
        )
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def _address_rows(self, billing_email="", shipping_email=""):
        return [
            {
                "name": "ADDR-BILL",
                "fieldname": "customer_address",
                "label": "Billing Address",
                "address_title": "Head Office",
                "email_id": billing_email,
            },
            {
                "name": "ADDR-SHIP",
                "fieldname": "shipping_address_name",
                "label": "Shipping Address",
                "address_title": "Warehouse",
                "email_id": shipping_email,
            },
        ]

    def test_receipt_addresses_skip_missing_and_duplicate_records(self):
        doc = self._order(customer_address="ADDR-1", shipping_address_name="ADDR-1")

        with patch.object(
            sales_orders.frappe.db,
            "get_value",
            return_value={"address_title": "Head Office", "email_id": "a@example.com"},
        ):
            rows = sales_orders._managed_sales_order_receipt_addresses(doc)

        self.assertEqual([row["name"] for row in rows], ["ADDR-1"])
        self.assertEqual(rows[0]["fieldname"], "customer_address")

    def test_receipt_state_points_at_the_address_the_recipient_came_from(self):
        doc = self._order()

        with patch.object(
            sales_orders,
            "_managed_sales_order_receipt_addresses",
            return_value=self._address_rows(shipping_email="ship@example.com"),
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="ship@example.com"
        ), patch.object(
            sales_orders, "_get_manual_receipt_email_settings", return_value=("POS Receipt", [])
        ):
            state = sales_orders._managed_sales_order_receipt_email_state(doc)

        self.assertEqual(state["recipient"], "ship@example.com")
        self.assertEqual(state["recipient_address"], "ADDR-SHIP")
        self.assertEqual(state["cc_emails"], [])
        self.assertTrue(state["can_send"])
        self.assertEqual(state["blocked_reason"], "")

    def test_receipt_state_blocks_when_print_format_is_missing(self):
        doc = self._order()

        with patch.object(
            sales_orders, "_managed_sales_order_receipt_addresses", return_value=[]
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="a@example.com"
        ), patch.object(
            sales_orders, "_get_manual_receipt_email_settings", return_value=("", [])
        ):
            state = sales_orders._managed_sales_order_receipt_email_state(doc)

        self.assertFalse(state["can_send"])
        self.assertIn("print format", state["blocked_reason"])

    def test_receipt_state_blocks_when_no_email_anywhere(self):
        doc = self._order()

        with patch.object(
            sales_orders, "_managed_sales_order_receipt_addresses", return_value=self._address_rows()
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value=""
        ), patch.object(
            sales_orders, "_get_manual_receipt_email_settings", return_value=("POS Receipt", [])
        ):
            state = sales_orders._managed_sales_order_receipt_email_state(doc)

        self.assertFalse(state["can_send"])
        self.assertEqual(state["recipient_address"], "")

    def test_manual_receipt_settings_ignore_the_auto_send_toggle(self):
        doc = self._order()

        with patch.object(
            sales_orders,
            "_get_receipt_email_settings",
            return_value=(0, "POS Receipt", ["cc@example.com"]),
        ):
            print_format, cc_emails = sales_orders._get_manual_receipt_email_settings(doc)

        self.assertEqual(print_format, "POS Receipt")
        self.assertEqual(cc_emails, ["cc@example.com"])

    def test_update_address_email_rejects_an_address_not_on_the_order(self):
        doc = self._order()

        with patch.object(
            sales_orders, "_managed_sales_order_receipt_addresses", return_value=self._address_rows()
        ), patch.object(sales_orders.frappe, "get_doc") as get_doc:
            with self.assertRaises(ValidationError):
                sales_orders._update_managed_sales_order_address_email(
                    doc, "ADDR-SOMEONE-ELSE", "new@example.com"
                )

        get_doc.assert_not_called()

    def test_update_address_email_rejects_an_invalid_email(self):
        doc = self._order()

        with patch.object(
            sales_orders, "_managed_sales_order_receipt_addresses", return_value=self._address_rows()
        ), patch.object(sales_orders.frappe, "get_doc") as get_doc:
            with self.assertRaises(ValidationError):
                sales_orders._update_managed_sales_order_address_email(doc, "ADDR-BILL", "not-an-email")

        get_doc.assert_not_called()

    def test_update_address_email_rejects_more_than_one_address(self):
        doc = self._order()

        with patch.object(
            sales_orders, "_managed_sales_order_receipt_addresses", return_value=self._address_rows()
        ), patch.object(sales_orders.frappe, "get_doc") as get_doc:
            with self.assertRaises(ValidationError):
                sales_orders._update_managed_sales_order_address_email(
                    doc, "ADDR-BILL", "a@example.com, b@example.com"
                )

        get_doc.assert_not_called()

    def test_update_address_email_saves_the_new_value(self):
        doc = self._order()
        address = SimpleNamespace(email_id="old@example.com", flags=SimpleNamespace(), save=MagicMock())

        with patch.object(
            sales_orders, "_managed_sales_order_receipt_addresses", return_value=self._address_rows()
        ), patch.object(sales_orders.frappe, "get_doc", return_value=address):
            result = sales_orders._update_managed_sales_order_address_email(
                doc, "ADDR-BILL", " New@Example.com "
            )

        self.assertEqual(result, "New@Example.com")
        self.assertEqual(address.email_id, "New@Example.com")
        address.save.assert_called_once_with(ignore_permissions=True)

    def test_update_address_email_is_a_no_op_when_unchanged(self):
        doc = self._order()
        address = SimpleNamespace(email_id="same@example.com", flags=SimpleNamespace(), save=MagicMock())

        with patch.object(
            sales_orders,
            "_managed_sales_order_receipt_addresses",
            return_value=self._address_rows(billing_email="same@example.com"),
        ), patch.object(sales_orders.frappe, "get_doc", return_value=address):
            sales_orders._update_managed_sales_order_address_email(doc, "ADDR-BILL", "same@example.com")

        address.save.assert_not_called()

    def test_resend_updates_the_address_then_enqueues_the_same_job(self):
        doc = self._order()

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_validate_managed_sales_order_doc"
        ), patch.object(
            sales_orders, "_update_managed_sales_order_address_email"
        ) as update_email, patch.object(
            sales_orders,
            "_get_manual_receipt_email_settings",
            return_value=("POS Receipt", ["cc@example.com"]),
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="new@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-9001"}
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            result = sales_orders.resend_managed_sales_order_receipt(
                "SO-9001", address="ADDR-BILL", email="new@example.com", include_cc=1
            )

        update_email.assert_called_once_with(doc, "ADDR-BILL", "new@example.com")
        enqueue.assert_called_once_with(
            "posawesome.posawesome.api.sales_orders._send_receipt_email_job",
            queue="short",
            enqueue_after_commit=True,
            sales_order_name="SO-9001",
            recipient="new@example.com",
            pos_profile="POS-1",
            print_format="POS Receipt",
            cc=["cc@example.com"],
            revised=False,
        )
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["recipient"], "new@example.com")

    def test_resend_leaves_the_address_alone_when_no_email_is_passed(self):
        doc = self._order()

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_validate_managed_sales_order_doc"
        ), patch.object(
            sales_orders, "_update_managed_sales_order_address_email"
        ) as update_email, patch.object(
            sales_orders, "_get_manual_receipt_email_settings", return_value=("POS Receipt", [])
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="existing@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-9001"}
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.resend_managed_sales_order_receipt("SO-9001")

        update_email.assert_not_called()
        enqueue.assert_called_once()

    def test_resend_reports_the_skip_instead_of_emailing_from_a_dev_site(self):
        doc = self._order()

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_validate_managed_sales_order_doc"
        ), patch.object(
            sales_orders, "_get_manual_receipt_email_settings", return_value=("POS Receipt", [])
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="customer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=True
        ), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-9001"}
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            result = sales_orders.resend_managed_sales_order_receipt("SO-9001")

        enqueue.assert_not_called()
        self.assertEqual(result["status"], "skipped_dev")
        self.assertEqual(result["recipient"], "customer@example.com")

    def test_resend_refuses_when_the_profile_has_no_print_format(self):
        doc = self._order()

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_validate_managed_sales_order_doc"
        ), patch.object(
            sales_orders, "_get_manual_receipt_email_settings", return_value=("", [])
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            with self.assertRaises(ValidationError):
                sales_orders.resend_managed_sales_order_receipt("SO-9001")

        enqueue.assert_not_called()

    def test_resend_refuses_when_there_is_no_recipient(self):
        doc = self._order()

        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_validate_managed_sales_order_doc"
        ), patch.object(
            sales_orders, "_get_manual_receipt_email_settings", return_value=("POS Receipt", [])
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value=""
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            with self.assertRaises(ValidationError):
                sales_orders.resend_managed_sales_order_receipt("SO-9001")

        enqueue.assert_not_called()

    def test_resend_requires_a_sales_order_name(self):
        with self.assertRaises(ValidationError):
            sales_orders.resend_managed_sales_order_receipt("   ")

    def test_receipt_state_exposes_the_profile_cc_list(self):
        doc = self._order()

        with patch.object(
            sales_orders, "_managed_sales_order_receipt_addresses", return_value=self._address_rows()
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="a@example.com"
        ), patch.object(
            sales_orders,
            "_get_manual_receipt_email_settings",
            return_value=("POS Receipt", ["office@example.com"]),
        ):
            state = sales_orders._managed_sales_order_receipt_email_state(doc)

        self.assertEqual(state["cc_emails"], ["office@example.com"])

    def _resend_with_cc(self, **kwargs):
        doc = self._order()
        with patch.object(sales_orders.frappe, "get_doc", return_value=doc), patch.object(
            sales_orders, "_validate_managed_sales_order_doc"
        ), patch.object(
            sales_orders,
            "_get_manual_receipt_email_settings",
            return_value=("POS Receipt", ["office@example.com"]),
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="customer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-9001"}
        ), patch.object(
            sales_orders.frappe, "enqueue"
        ) as enqueue:
            sales_orders.resend_managed_sales_order_receipt("SO-9001", **kwargs)
        return enqueue

    def test_resend_drops_the_cc_list_unless_it_is_opted_into(self):
        enqueue = self._resend_with_cc()

        self.assertEqual(enqueue.call_args.kwargs["cc"], [])

    def test_resend_drops_the_cc_list_when_the_box_is_unticked(self):
        enqueue = self._resend_with_cc(include_cc=0)

        self.assertEqual(enqueue.call_args.kwargs["cc"], [])

    def test_resend_includes_the_cc_list_when_opted_into(self):
        enqueue = self._resend_with_cc(include_cc=1)

        self.assertEqual(enqueue.call_args.kwargs["cc"], ["office@example.com"])

    def test_resend_accepts_the_opt_in_as_a_string_from_the_client(self):
        # frappe.call sends checkbox values as "1"/"0", not booleans.
        enqueue = self._resend_with_cc(include_cc="1")

        self.assertEqual(enqueue.call_args.kwargs["cc"], ["office@example.com"])
