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
    frappe_module.get_meta = lambda *args, **kwargs: SimpleNamespace(
        get_field=lambda fieldname: SimpleNamespace(options="")
    )
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
        sql=lambda *args, **kwargs: [],
    )
    frappe_module.conf = {}
    frappe_module.local = SimpleNamespace(conf={}, site="")

    frappe_utils = types.ModuleType("frappe.utils")
    frappe_utils.cint = lambda value=0: int(value or 0)
    frappe_utils.cstr = lambda value="": "" if value is None else str(value)
    frappe_utils.flt = lambda value=0, precision=None, *args, **kwargs: round(float(value or 0), precision) if precision is not None else float(value or 0)
    frappe_utils.getdate = lambda value: value
    frappe_utils.nowdate = lambda: "2026-06-15"
    frappe_utils.validate_email_address = lambda email_str, throw=False: (email_str or "")
    frappe_utils.split_emails = lambda txt: [
        email.strip() for email in str(txt or "").replace("\n", ",").split(",") if email.strip()
    ]

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

    def test_get_managed_sales_orders_sort_by_options(self):
        def capture(sort_by):
            captured = {}

            def fake_get_list(*args, **kwargs):
                captured.update(kwargs)
                return []

            with patch.object(sales_orders.frappe, "get_list", side_effect=fake_get_list):
                sales_orders.get_managed_sales_orders("Test Company", "GBP", sort_by=sort_by)
            return captured["order_by"]

        self.assertEqual(capture(None), "transaction_date desc, name desc")
        self.assertEqual(capture("transaction_date"), "transaction_date desc, name desc")
        self.assertEqual(capture("modified"), "modified desc")
        # Unknown / hostile values fall back to the default rather than reaching the query.
        self.assertEqual(capture("name asc; DROP TABLE"), "transaction_date desc, name desc")

    def test_get_managed_sales_orders_status_filter(self):
        def capture(status):
            captured = {}

            def fake_get_list(*args, **kwargs):
                captured.update(kwargs)
                return []

            with patch.object(sales_orders.frappe, "get_list", side_effect=fake_get_list):
                sales_orders.get_managed_sales_orders("Test Company", "GBP", status=status)
            return captured["filters"]

        # No status selected leaves the listing unfiltered on status.
        self.assertNotIn("status", capture(None))
        self.assertNotIn("status", capture(""))
        self.assertNotIn("status", capture("   "))
        self.assertEqual(capture("To Deliver and Bill")["status"], "To Deliver and Bill")

    def test_managed_sales_order_statuses_exclude_non_submitted(self):
        meta = SimpleNamespace(
            get_field=lambda fieldname: SimpleNamespace(
                options="\nDraft\nOn Hold\nTo Pay\nTo Deliver and Bill\nCompleted\nCancelled\nClosed"
            )
        )
        with patch.object(sales_orders.frappe, "get_meta", return_value=meta):
            statuses = sales_orders.get_managed_sales_order_statuses()

        # Draft and Cancelled can never appear in a docstatus=1 listing.
        self.assertEqual(statuses, ["On Hold", "To Pay", "To Deliver and Bill", "Completed", "Closed"])

    def test_delivery_charge_prefers_field_then_falls_back_to_tax_row(self):
        # Field present: used directly, along with its stored rate.
        doc = SimpleNamespace(
            posa_delivery_charges="Standard Delivery",
            posa_delivery_charges_rate=25,
            taxes=[],
        )
        self.assertEqual(sales_orders._get_managed_sales_order_delivery_charge(doc), ("Standard Delivery", 25))

        # Field missing on this site: recovered from the Actual tax row it wrote.
        doc = SimpleNamespace(
            taxes=[
                SimpleNamespace(charge_type="On Net Total", description="VAT", tax_amount=40),
                SimpleNamespace(charge_type="Actual", description="Collect From Store", tax_amount=15),
            ]
        )
        with patch.object(sales_orders.frappe.db, "exists", side_effect=lambda dt, name: name == "Collect From Store"):
            self.assertEqual(
                sales_orders._get_managed_sales_order_delivery_charge(doc), ("Collect From Store", 15)
            )

        # An Actual row that is not a Delivery Charges record is not mistaken for one.
        doc = SimpleNamespace(taxes=[SimpleNamespace(charge_type="Actual", description="Handling", tax_amount=5)])
        with patch.object(sales_orders.frappe.db, "exists", return_value=False):
            self.assertEqual(sales_orders._get_managed_sales_order_delivery_charge(doc), ("", 0))

    def test_payment_types_net_refunds_and_drop_blank_modes(self):
        rows = [
            {"mode_of_payment": "Cash", "amount": 100},
            {"mode_of_payment": "", "amount": 20},
            {"mode_of_payment": "Card", "amount": -10},
        ]
        with patch.object(sales_orders.frappe.db, "sql", return_value=rows):
            payments = sales_orders._get_managed_sales_order_payment_types("SO-1")

        self.assertEqual(
            payments,
            [{"mode_of_payment": "Cash", "amount": 100.0}, {"mode_of_payment": "Card", "amount": -10.0}],
        )

    def test_stream_pick_list_links_require_a_safe_openable_url(self):
        status_rows = [
            {"name": "PICK-3", "status": "Completed", "stream_id": "C3", "stream_status": "Delivered",
             "tracking_link": "https://stream.example/track/C3"},
            {"name": "PICK-1", "status": "Open", "stream_id": "C1", "stream_status": "In Transit",
             "tracking_link": "http://stream.example/track/C1"},
            # In Stream but nothing to open.
            {"name": "PICK-2", "status": "Open", "stream_id": "C2", "stream_status": "Booked",
             "tracking_link": ""},
            # Never linked to Stream at all.
            {"name": "PICK-4", "status": "Open"},
            # Third-party data, so a non-http scheme must not become a clickable link.
            {"name": "PICK-5", "status": "Open", "stream_id": "C5",
             "tracking_link": "javascript:alert(1)"},
        ]

        links = sales_orders._build_stream_pick_list_links(status_rows)

        self.assertEqual([entry["name"] for entry in links], ["PICK-1", "PICK-3"])
        self.assertEqual(links[0]["tracking_link"], "http://stream.example/track/C1")
        self.assertEqual(links[0]["stream_status"], "In Transit")

    def test_pick_list_stream_fields_skip_columns_the_site_lacks(self):
        with patch.object(sales_orders.frappe.db, "has_column", side_effect=lambda dt, f: f == "stream_id"):
            self.assertEqual(sales_orders._pick_list_stream_fields(), ["stream_id"])

    def test_shipping_address_surfaces_phone_as_the_mobile_number(self):
        doc = SimpleNamespace(shipping_address_name="ADDR-SHIP", shipping_address="1 High St<br>Leeds")
        values = {
            "address_title": " Jane Smith ",
            "address_type": "Shipping",
            "address_line1": "1 High St",
            "address_line2": "",
            "city": "Leeds",
            "county": "West Yorkshire",
            "state": "",
            "pincode": "LS1 1AA",
            "country": "United Kingdom",
            "email_id": "jane@example.com",
            # POS Awesome writes the customer's mobile into the Address phone field.
            "phone": "07123456789",
        }
        with patch.object(sales_orders.frappe.db, "get_value", return_value=values):
            address = sales_orders._get_managed_sales_order_shipping_address(doc)

        self.assertEqual(address["name"], "ADDR-SHIP")
        self.assertEqual(address["phone"], "07123456789")
        self.assertEqual(address["address_title"], "Jane Smith")
        self.assertEqual(address["display"], "1 High St<br>Leeds")

    def test_shipping_address_absent_returns_none(self):
        self.assertIsNone(
            sales_orders._get_managed_sales_order_shipping_address(SimpleNamespace(shipping_address_name=""))
        )

        # Link set but the Address record is gone.
        doc = SimpleNamespace(shipping_address_name="ADDR-GONE")
        with patch.object(sales_orders.frappe.db, "get_value", return_value=None):
            self.assertIsNone(sales_orders._get_managed_sales_order_shipping_address(doc))

    def test_get_managed_sales_order_returns_component_due_date_context(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-1",
            docstatus=1,
            rfs_order=1,
            is_pos=1,
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
            is_pos=1,
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
            is_pos=1,
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
            is_pos=1,
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
            is_pos=1,
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
            is_pos=1,
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

    def _managed_items_order(self, name, items):
        return SimpleNamespace(
            doctype="Sales Order",
            name=name,
            docstatus=1,
            rfs_order=1,
            is_pos=1,
            customer="RFS-001",
            pos_profile="Main POS",
            selling_price_list="Retail",
            currency="GBP",
            delivery_date="2026-07-30",
            reload=MagicMock(),
            items=items,
        )

    def _existing_managed_item(self):
        return SimpleNamespace(
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
            bom_no=None,
            conversion_factor=1,
        )

    def test_update_managed_sales_order_items_keeps_client_rate_on_new_rows(self):
        so_doc = self._managed_items_order("SO-MANAGED-ITEMS-NEW", [self._existing_managed_item()])

        payload = {
            "name": "SO-MANAGED-ITEMS-NEW",
            "items": [
                {
                    "docname": "SOI-EDITABLE",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 1,
                    "conversion_factor": 1,
                    # Ignored: existing rows always keep their stored price.
                    "rate": 5,
                },
                {
                    "item_code": "ITEM-NEW",
                    "uom": "Box",
                    "description": "Brand new line",
                    "bom_no": None,
                    "qty": 3,
                    "conversion_factor": 2,
                    "rate": 42.5,
                },
            ],
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-MANAGED-ITEMS-NEW"}
        ), patch.object(
            sales_orders, "_resolve_managed_sales_order_item_pricing"
        ) as resolve_pricing, patch(
            "customer_due_dates.api.update_child_qty_rate.update_child_qty_rate"
        ) as update_items:
            sales_orders.update_managed_sales_order_items(payload)

        # A rate the user typed on a new row is used as-is, so no pricing lookup.
        resolve_pricing.assert_not_called()
        rows = json.loads(update_items.call_args.kwargs["trans_items"])
        existing_row, new_row = rows

        self.assertEqual(existing_row["docname"], "SOI-EDITABLE")
        self.assertEqual(existing_row["rate"], 100.0)
        self.assertIsNone(new_row["docname"])
        self.assertEqual(new_row["item_code"], "ITEM-NEW")
        self.assertEqual(new_row["rate"], 42.5)
        self.assertEqual(new_row["qty"], 3.0)
        # Left for set_order_defaults to resolve from the Item and the parent.
        self.assertIsNone(new_row["warehouse"])
        self.assertIsNone(new_row["delivery_date"])

    def test_update_managed_sales_order_items_prices_new_rows_without_a_rate(self):
        so_doc = self._managed_items_order("SO-MANAGED-ITEMS-PRICED", [self._existing_managed_item()])

        payload = {
            "name": "SO-MANAGED-ITEMS-PRICED",
            "items": [
                {
                    "item_code": "ITEM-NEW",
                    "uom": "Nos",
                    "description": "Brand new line",
                    "bom_no": None,
                    "qty": 1,
                    "conversion_factor": 1,
                },
            ],
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-MANAGED-ITEMS-PRICED"}
        ), patch.object(
            sales_orders, "_resolve_managed_sales_order_item_pricing", return_value={"rate": 17.5}
        ) as resolve_pricing, patch(
            "customer_due_dates.api.update_child_qty_rate.update_child_qty_rate"
        ) as update_items:
            sales_orders.update_managed_sales_order_items(payload)

        resolve_pricing.assert_called_once_with(so_doc, "ITEM-NEW", "Nos")
        rows = json.loads(update_items.call_args.kwargs["trans_items"])
        self.assertEqual(rows[0]["rate"], 17.5)

    def test_update_managed_sales_order_items_rejects_unknown_docname(self):
        so_doc = self._managed_items_order("SO-MANAGED-ITEMS-STALE", [self._existing_managed_item()])

        payload = {
            "name": "SO-MANAGED-ITEMS-STALE",
            "items": [
                {
                    "docname": "SOI-GONE",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 1,
                    "conversion_factor": 1,
                },
            ],
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc):
            with self.assertRaisesRegex(RuntimeError, "no longer exists"):
                sales_orders.update_managed_sales_order_items(payload)

    def test_update_managed_sales_order_items_allows_untouched_locked_rows(self):
        """A picked row that is sent back unchanged must not block the save.

        The incoming row is enriched with rate/warehouse/delivery_date before the
        mutation check runs, so it is only comparable against the stored row on the
        fields the client can actually influence.
        """
        picked_row = self._existing_managed_item()
        picked_row.name = "SOI-PICKED"
        picked_row.picked_qty = 1

        editable_row = self._existing_managed_item()
        editable_row.name = "SOI-OPEN"

        so_doc = self._managed_items_order("SO-MANAGED-ITEMS-MIXED", [picked_row, editable_row])

        payload = {
            "name": "SO-MANAGED-ITEMS-MIXED",
            "items": [
                {
                    "docname": "SOI-PICKED",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 1,
                    "conversion_factor": 1,
                },
                {
                    "docname": "SOI-OPEN",
                    "item_code": "ITEM-1",
                    "uom": "Nos",
                    "description": "Desc 1",
                    "bom_no": None,
                    "qty": 4,
                    "conversion_factor": 1,
                },
            ],
        }

        with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
            sales_orders, "_serialize_managed_sales_order", return_value={"name": "SO-MANAGED-ITEMS-MIXED"}
        ), patch(
            "customer_due_dates.api.update_child_qty_rate.update_child_qty_rate"
        ) as update_items:
            sales_orders.update_managed_sales_order_items(payload)

        rows = json.loads(update_items.call_args.kwargs["trans_items"])
        self.assertEqual([row["qty"] for row in rows], [1.0, 4.0])

    def test_queue_receipt_email_flags_a_revision(self):
        doc = SimpleNamespace(name="SO-RECEIPT-1", pos_profile="Main POS")
        captured = {}

        def fake_enqueue(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt", ["ops@x.com"])
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="buyer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders.frappe, "enqueue", fake_enqueue
        ):
            sales_orders._queue_receipt_email(doc, revised=True)

        kwargs = captured["kwargs"]
        self.assertTrue(kwargs["revised"])
        self.assertEqual(kwargs["sales_order_name"], "SO-RECEIPT-1")
        self.assertEqual(kwargs["recipient"], "buyer@example.com")
        # Must not email a receipt for a change that gets rolled back.
        self.assertTrue(kwargs["enqueue_after_commit"])

    def test_queue_receipt_email_defaults_to_original_wording(self):
        doc = SimpleNamespace(name="SO-RECEIPT-2", pos_profile="Main POS")
        captured = {}

        with patch.object(
            sales_orders, "_should_auto_email_receipt", return_value=(True, "POS Receipt", [])
        ), patch.object(
            sales_orders, "_resolve_customer_email", return_value="buyer@example.com"
        ), patch.object(
            sales_orders, "_is_dev_or_local_environment", return_value=False
        ), patch.object(
            sales_orders.frappe, "enqueue", lambda *a, **k: captured.update(k)
        ):
            sales_orders.on_submit(doc, "on_submit")

        self.assertFalse(captured["revised"])

    def test_receipt_job_subject_differs_for_a_revision(self):
        so_doc = SimpleNamespace(name="SO-RECEIPT-3", doctype="Sales Order")
        sent = []

        def run(revised):
            sent.clear()
            with patch.object(sales_orders.frappe, "get_doc", return_value=so_doc), patch.object(
                sales_orders, "_build_receipt_attachment", return_value={"fcontent": b"pdf"}
            ), patch.object(
                sales_orders, "_get_receipt_sender", return_value="pos@example.com"
            ), patch.object(
                sales_orders.frappe, "sendmail", lambda **kwargs: sent.append(kwargs)
            ):
                sales_orders._send_receipt_email_job(
                    "SO-RECEIPT-3", "buyer@example.com", print_format="POS Receipt", revised=revised
                )
            return sent[0]

        revised = run(True)
        original = run(False)
        self.assertIn("Updated Receipt", revised["subject"])
        self.assertIn("revised receipt", revised["message"])
        self.assertNotIn("Updated Receipt", original["subject"])
        self.assertIn("SO-RECEIPT-3", revised["subject"])

    def test_update_managed_sales_order_items_blocks_picked_rows(self):
        so_doc = SimpleNamespace(
            doctype="Sales Order",
            name="SO-MANAGED-ITEMS-2",
            docstatus=1,
            rfs_order=1,
            is_pos=1,
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
            is_pos=1,
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
            is_pos=1,
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

    def test_copy_group_order_payload_only_first_group_carries_delivery_charge(self):
        order = {
            "doctype": "Sales Order",
            "posa_delivery_charges": "Standard Delivery",
            "posa_delivery_charges_rate": 5.0,
            "taxes": [
                {
                    "charge_type": "Actual",
                    "description": "Standard Delivery",
                    "tax_amount": 5.0,
                    "account_head": "Shipping - TC",
                }
            ],
            "items": [
                {"item_code": "ITEM-1", "posa_row_id": "row-1", "qty": 1, "rate": 100},
                {"item_code": "ITEM-2", "posa_row_id": "row-2", "qty": 1, "rate": 200},
            ],
        }
        item_map = {item["posa_row_id"]: item for item in order["items"]}

        first_payload = sales_orders._copy_group_order_payload(
            order,
            {"group_id": "living", "label": "Living", "row_ids": ["row-1"]},
            item_map,
            "ORBASE1234-01",
            carries_delivery_charge=True,
        )
        second_payload = sales_orders._copy_group_order_payload(
            order,
            {"group_id": "bedroom", "label": "Bedroom", "row_ids": ["row-2"]},
            item_map,
            "ORBASE1234-02",
            carries_delivery_charge=False,
        )

        self.assertEqual(first_payload["posa_delivery_charges"], "Standard Delivery")
        self.assertEqual(first_payload["posa_delivery_charges_rate"], 5.0)
        self.assertEqual(len(first_payload["taxes"]), 1)

        self.assertEqual(second_payload["posa_delivery_charges"], "")
        self.assertEqual(second_payload["posa_delivery_charges_rate"], 0)
        self.assertEqual(second_payload["taxes"], [])

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
