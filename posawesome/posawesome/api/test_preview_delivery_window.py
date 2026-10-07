import json
import sys
import types
import unittest
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from test_sales_order_submit import FakeSalesOrder, sales_orders


class FakePreviewSalesOrder(FakeSalesOrder):
    def __init__(self):
        super().__init__()
        self.items = [
            SimpleNamespace(name="soi-1", posa_row_id="row-a", item_code="SOFA-1", item_name="Sofa", qty=1, quoted_date="2026-11-04"),
            SimpleNamespace(name="soi-2", posa_row_id="row-b", item_code="TABLE-1", item_name="Table", qty=2, quoted_date="2026-10-07"),
        ]
        self.latest_quoted_date = None
        self.quoted_estimated_delivery_window = None

    def save(self):
        self.saved_with_docstatus = self.docstatus


class TestPreviewQuotedDeliveryWindow(TestCase):
    def setUp(self):
        self.db = sales_orders.frappe.db
        self.db._disable_transaction_control = 0
        self.original_commit = MagicMock(name="commit")
        self.db.commit = self.original_commit
        self.db.rollback = MagicMock(name="rollback")
        self.db.exists = lambda *args, **kwargs: False
        sales_orders.frappe.clear_document_cache = MagicMock()

        self.doc = FakePreviewSalesOrder()
        self.calls = []

        def auto_allocate(doc):
            self.calls.append(("allocate", doc.docstatus))
            doc.latest_quoted_date = "2026-11-18"
            doc.quoted_estimated_delivery_window = "23-11-2026 - 27-11-2026"

        cdd_override = types.ModuleType("customer_due_dates.kit_items.overrides.sales_order")
        cdd_override.auto_allocate_on_so_submit = auto_allocate
        rfs = types.ModuleType("customer_due_dates.utils.rfs_customer")
        rfs.apply_sales_order_naming_series = lambda doc, force=False: self.calls.append(("naming", force))
        rfs.is_rfs_customer = lambda customer: False
        due_dates = types.ModuleType("customer_due_dates.item_due_dates.prealloc.due_dates")
        due_dates._is_ns_item = lambda item_code: (item_code or "").lower().startswith("ns-")
        alloc_fields = types.ModuleType("customer_due_dates.item_due_dates.prealloc.so_alloc_fields")
        alloc_fields._preallocated_outstanding_for_soi = lambda name: 1 if name == "soi-1" else 0
        alloc_fields._reserved_for_soi = lambda name: 2 if name == "soi-2" else 0

        self.module_patch = patch.dict(
            sys.modules,
            {
                "customer_due_dates.kit_items.overrides.sales_order": cdd_override,
                "customer_due_dates.utils.rfs_customer": rfs,
                "customer_due_dates.item_due_dates.prealloc.so_alloc_fields": alloc_fields,
                "customer_due_dates.item_due_dates.prealloc.due_dates": due_dates,
            },
        )
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)

        for helper in (
            "_map_delivery_dates",
            "_apply_ns_default_warehouse",
            "_force_peterborough_store_collection",
            "_sync_shopify_notes_from_posa",
            "_apply_kit_meta_fields",
            "_apply_delivery_charges_tax_row",
        ):
            p = patch.object(sales_orders, helper, side_effect=lambda *a, _h=helper: self.calls.append((_h,)))
            p.start()
            self.addCleanup(p.stop)

        get_doc_patch = patch.object(sales_orders.frappe, "get_doc", return_value=self.doc)
        self.get_doc = get_doc_patch.start()
        self.addCleanup(get_doc_patch.stop)

    def _order(self, **extra):
        order = {"doctype": "Sales Order", "customer": "C-1", "items": [], "payments": [{"amount": 10}]}
        order.update(extra)
        return json.dumps(order)

    def test_returns_window_and_line_sources_then_rolls_back(self):
        result = sales_orders.preview_quoted_delivery_window(self._order())

        self.assertEqual(result["window"], "23-11-2026 - 27-11-2026")
        self.assertEqual(result["latest_quoted_date"], "2026-11-18")
        self.assertFalse(result["is_rfs"])
        self.assertEqual([line["source"] for line in result["lines"]], ["On Order", "In Stock"])
        self.assertEqual([line["posa_row_id"] for line in result["lines"]], ["row-a", "row-b"])
        self.assertEqual(self.doc.saved_with_docstatus, 0)
        self.assertIn(("allocate", 1), self.calls)
        self.assertIn(("naming", True), self.calls)
        self.db.rollback.assert_called_once_with()
        self.assertIs(self.db.commit, self.original_commit)
        self.original_commit.assert_not_called()

    def test_ns_items_are_labelled_allocated(self):
        self.doc.items.append(
            SimpleNamespace(
                name="soi-3", posa_row_id="row-c", item_code="NS-CUSTOM", item_name="Custom", qty=1, quoted_date="2026-10-07"
            )
        )

        result = sales_orders.preview_quoted_delivery_window(self._order())

        self.assertEqual(result["lines"][2]["source"], "In Stock")

    def test_payments_are_dropped_and_submit_prep_applied(self):
        sales_orders.preview_quoted_delivery_window(self._order())

        payload = self.get_doc.call_args.args[0]
        self.assertNotIn("payments", payload)
        for helper in ("_map_delivery_dates", "_apply_ns_default_warehouse", "_force_peterborough_store_collection"):
            self.assertIn((helper,), self.calls)

    def test_commit_inside_preview_is_blocked_and_rolled_back(self):
        def committing_allocate(doc):
            sales_orders.frappe.db.commit()

        sys.modules["customer_due_dates.kit_items.overrides.sales_order"].auto_allocate_on_so_submit = (
            committing_allocate
        )

        with self.assertRaises(sales_orders._PreviewCommitBlocked):
            sales_orders.preview_quoted_delivery_window(self._order())

        self.original_commit.assert_not_called()
        self.db.rollback.assert_called_once_with()
        self.assertIs(self.db.commit, self.original_commit)

    def test_rolls_back_when_save_raises(self):
        self.doc.save = MagicMock(side_effect=RuntimeError("Customer is mandatory"))

        with self.assertRaises(RuntimeError):
            sales_orders.preview_quoted_delivery_window(self._order())

        self.db.rollback.assert_called_once_with()

    def test_existing_draft_is_updated_and_cache_cleared(self):
        self.db.exists = lambda *args, **kwargs: True

        sales_orders.preview_quoted_delivery_window(self._order(name="SO-DRAFT-1"))

        self.get_doc.assert_called_once_with("Sales Order", "SO-DRAFT-1")
        self.assertNotIn(("naming", True), self.calls)
        sales_orders.frappe.clear_document_cache.assert_called_once_with("Sales Order", "SO-DRAFT-1")

    def test_split_delivery_cart_is_estimated_as_one_order(self):
        result = sales_orders.preview_quoted_delivery_window(
            self._order(
                posa_split_delivery=1,
                must_be_fully_allocated=0,
                posa_split_groups=[{"group_id": "default", "label": "Group 1", "row_ids": ["row-a"]}],
            )
        )

        payload = self.get_doc.call_args.args[0]
        self.assertEqual(payload["posa_split_delivery"], 0)
        self.assertEqual(payload["must_be_fully_allocated"], 1)
        self.assertNotIn("posa_split_groups", payload)
        self.assertEqual(result["window"], "23-11-2026 - 27-11-2026")

    def test_refuses_when_transaction_control_is_disabled(self):
        self.db._disable_transaction_control = 1

        with self.assertRaises(RuntimeError):
            sales_orders.preview_quoted_delivery_window(self._order())

        self.db.rollback.assert_not_called()


    def test_split_groups_are_allocated_in_order_then_rolled_back(self):
        first, second = FakePreviewSalesOrder(), FakePreviewSalesOrder()
        windows = iter(["06-07-2026 - 10-07-2026", "13-07-2026 - 17-07-2026"])

        def auto_allocate(doc):
            self.calls.append(("allocate", id(doc), doc.docstatus))
            doc.quoted_estimated_delivery_window = next(windows)

        sys.modules["customer_due_dates.kit_items.overrides.sales_order"].auto_allocate_on_so_submit = auto_allocate
        built = [
            {"group_id": "default", "label": "In Stock", "doc": first},
            {"group_id": "supply-back-order", "label": "Back Order", "doc": second},
        ]
        with patch.object(sales_orders, "_build_split_group_documents", return_value=built) as build:
            result = sales_orders.preview_split_group_delivery_windows(self._order(posa_split_groups=[{}]))

        order = build.call_args.args[0]
        self.assertNotIn("payments", order)
        self.assertEqual(order["posa_split_delivery"], 1)
        self.assertEqual(
            [call for call in self.calls if call[0] == "allocate"],
            [("allocate", id(first), 1), ("allocate", id(second), 1)],
        )
        self.assertEqual(
            result["groups"],
            [
                {"group_id": "default", "label": "In Stock", "window": "06-07-2026 - 10-07-2026"},
                {"group_id": "supply-back-order", "label": "Back Order", "window": "13-07-2026 - 17-07-2026"},
            ],
        )
        self.db.rollback.assert_called_once_with()
        self.original_commit.assert_not_called()

    def test_split_preview_rolls_back_when_group_build_fails(self):
        with patch.object(sales_orders, "_build_split_group_documents", side_effect=RuntimeError("no groups")):
            with self.assertRaises(RuntimeError):
                sales_orders.preview_split_group_delivery_windows(self._order())

        self.db.rollback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
