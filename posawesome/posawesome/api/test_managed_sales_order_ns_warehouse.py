"""An NS line added from Sales Order Management keeps the warehouse it was given.

Runs on the same stubbed-frappe harness as test_sales_order_submit, so it needs no
site: these are pure decisions about what warehouse a row is saved with.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from test_sales_order_submit import sales_orders


def _order(pos_profile="Main POS", company="Test Company", items=None):
    return SimpleNamespace(
        name="SO-TEST-0001",
        company=company,
        pos_profile=pos_profile,
        customer="Test Customer",
        currency="GBP",
        delivery_date="2026-07-30",
        items=items or [],
    )


def _existing_row(name="SOI-1", item_code="NS-1001", warehouse="NS Annexe - TC"):
    return SimpleNamespace(
        name=name,
        item_code=item_code,
        warehouse=warehouse,
        uom="Nos",
        description="Existing row",
        bom_no=None,
        qty=1,
        conversion_factor=1,
        rate=25,
        delivery_date="2026-07-30",
    )


class TestNewItemWarehouseResolution(TestCase):
    def test_ns_row_falls_back_to_the_profile_default(self):
        warehouse = sales_orders._resolve_new_managed_sales_order_item_warehouse(
            _order(), "NS-1001", None, "NS Main - TC"
        )
        self.assertEqual(warehouse, "NS Main - TC")

    def test_ns_row_keeps_the_warehouse_that_was_chosen(self):
        with patch.object(sales_orders.frappe.db, "get_value", return_value="Test Company"):
            warehouse = sales_orders._resolve_new_managed_sales_order_item_warehouse(
                _order(), "NS-1001", "NS Annexe - TC", "NS Main - TC"
            )
        self.assertEqual(warehouse, "NS Annexe - TC")

    def test_non_ns_row_is_left_to_the_item_default(self):
        """A stock line is not placed by POS, so a warehouse on it is ignored."""
        warehouse = sales_orders._resolve_new_managed_sales_order_item_warehouse(
            _order(), "ITEM-1001", "NS Annexe - TC", "NS Main - TC"
        )
        self.assertIsNone(warehouse)

    def test_unknown_warehouse_is_rejected(self):
        with patch.object(sales_orders.frappe.db, "get_value", return_value=None):
            with self.assertRaises(RuntimeError) as caught:
                sales_orders._resolve_new_managed_sales_order_item_warehouse(
                    _order(), "NS-1001", "Nowhere - TC", "NS Main - TC"
                )
        self.assertIn("Nowhere - TC", str(caught.exception))

    def test_warehouse_from_another_company_is_rejected(self):
        with patch.object(sales_orders.frappe.db, "get_value", return_value="Other Company"):
            with self.assertRaises(RuntimeError) as caught:
                sales_orders._resolve_new_managed_sales_order_item_warehouse(
                    _order(), "NS-1001", "NS Elsewhere - OC", "NS Main - TC"
                )
        self.assertIn("Test Company", str(caught.exception))

    def test_order_with_no_pos_profile_has_no_ns_default(self):
        self.assertEqual(
            sales_orders._get_managed_sales_order_ns_default_warehouse(_order(pos_profile=None)), ""
        )


class TestPreparedRowWarehouses(TestCase):
    def _prepare(self, doc, incoming):
        with patch.object(
            sales_orders, "_get_managed_sales_order_ns_default_warehouse", return_value="NS Main - TC"
        ), patch.object(
            sales_orders,
            "_resolve_managed_sales_order_item_pricing",
            return_value={"rate": 99.0},
        ), patch.object(
            sales_orders.frappe.db, "get_value", return_value="Test Company"
        ):
            return sales_orders._prepare_managed_sales_order_item_rows(doc, incoming)

    def test_new_ns_row_carries_the_chosen_warehouse(self):
        rows = self._prepare(
            _order(),
            [{"item_code": "NS-1001", "uom": "Nos", "qty": 1, "warehouse": "NS Annexe - TC"}],
        )
        self.assertEqual(rows[0]["warehouse"], "NS Annexe - TC")

    def test_new_ns_row_without_a_choice_uses_the_default(self):
        rows = self._prepare(_order(), [{"item_code": "NS-1001", "uom": "Nos", "qty": 1}])
        self.assertEqual(rows[0]["warehouse"], "NS Main - TC")

    def test_existing_row_keeps_its_stored_warehouse(self):
        """The client cannot move a line that is already on the order."""
        existing = _existing_row()
        rows = self._prepare(
            _order(items=[existing]),
            [
                {
                    "docname": "SOI-1",
                    "item_code": "NS-1001",
                    "uom": "Nos",
                    "qty": 2,
                    "warehouse": "NS Main - TC",
                }
            ],
        )
        self.assertEqual(rows[0]["warehouse"], "NS Annexe - TC")

    def test_locked_row_comparison_ignores_the_warehouse(self):
        """Enriched fields must not make an untouched locked row look modified."""
        shape = sales_orders._managed_sales_order_item_compare_shape(
            {"docname": "SOI-1", "item_code": "NS-1001", "warehouse": "NS Annexe - TC"}
        )
        self.assertNotIn("warehouse", shape)
