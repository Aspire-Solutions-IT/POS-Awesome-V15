"""Adding a row to a submitted Sales Order as a restricted login (partner).

item_code on Sales Order Item is permlevel 1 and the POS Sales Partner role can only
read it, so Frappe's validate_higher_perm_levels blanked it on the new row and the insert
failed with "Mandatory: item_code". The managed-update guard now lets rows being
inserted into the order being updated through. These tests run on the stubbed-frappe
harness (plain python3), with a stand-in for the real reset that blanks item_code.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import test_partner_pricing as tpp
from test_sales_order_submit import sales_orders


class FakeDoc:
    """A document with just what the guard reads, and a faithful-enough reset."""

    def __init__(self, doctype, name, parenttype=None, parent=None, new=False, istable=False):
        self.doctype = doctype
        self.name = name
        self.parenttype = parenttype
        self.parent = parent
        self._new = new
        self.meta = SimpleNamespace(istable=1 if istable else 0)
        self.item_code = "WIDGET"

    def get(self, key, default=None):
        return getattr(self, key, default)

    def is_new(self):
        return self._new


def _child(parent="SO-1", parenttype="Sales Order", new=True):
    return FakeDoc("Sales Order Item", "new-sales-order-item-abc", parenttype, parent, new, True)


def _real_reset(self):
    """Stand-in for Document.validate_higher_perm_levels as a partner: permlevel-1
    fields (item_code) are put back to the empty default of a new record."""
    self.item_code = None


class TestAddRowPermlevelGuard(unittest.TestCase):
    def setUp(self):
        from frappe.model.document import Document

        self.Document = Document
        self._saved = Document.validate_higher_perm_levels
        Document.validate_higher_perm_levels = _real_reset

    def tearDown(self):
        self.Document.validate_higher_perm_levels = self._saved

    def _run(self, doc):
        with sales_orders._keep_computed_fields_on_save("Sales Order", "SO-1"):
            self.Document.validate_higher_perm_levels(doc)
        return doc

    def test_without_the_guard_item_code_is_blanked(self):
        doc = _child()
        self.Document.validate_higher_perm_levels(doc)
        self.assertIsNone(doc.item_code)

    def test_new_row_of_the_order_keeps_item_code(self):
        self.assertEqual(self._run(_child()).item_code, "WIDGET")

    def test_parent_order_still_skipped(self):
        doc = FakeDoc("Sales Order", "SO-1")
        self.assertEqual(self._run(doc).item_code, "WIDGET")

    def test_other_orders_row_is_still_reset(self):
        self.assertIsNone(self._run(_child(parent="SO-2")).item_code)

    def test_row_of_another_parent_doctype_is_still_reset(self):
        self.assertIsNone(self._run(_child(parenttype="Quotation")).item_code)

    def test_a_different_doctype_is_still_reset(self):
        # Another child table of the same order, and a different doctype altogether.
        taxes = FakeDoc("Sales Taxes and Charges", "t", "Sales Order", "SO-1", True, True)
        self.assertIsNone(self._run(taxes).item_code)
        payment = FakeDoc("Payment Entry", "SO-1", "Sales Order", "SO-1", True, True)
        self.assertIsNone(self._run(payment).item_code)

    def test_other_order_with_same_name_but_not_a_row_is_reset(self):
        self.assertIsNone(self._run(FakeDoc("Sales Order", "SO-2")).item_code)

    def test_non_table_doc_pointing_at_the_order_is_reset(self):
        doc = FakeDoc("Sales Order Item", "x", "Sales Order", "SO-1", True, False)
        self.assertIsNone(self._run(doc).item_code)

    def test_already_saved_row_is_not_matched_by_the_child_clause(self):
        self.assertIsNone(self._run(_child(new=False)).item_code)

    def test_patch_is_restored_even_when_the_update_fails(self):
        with self.assertRaises(RuntimeError):
            with sales_orders._keep_computed_fields_on_save("Sales Order", "SO-1"):
                raise RuntimeError("boom")
        self.assertIs(self.Document.validate_higher_perm_levels, _real_reset)
        self.assertIsNone(_run_plain(_child()).item_code)


def _run_plain(doc):
    from frappe.model.document import Document

    Document.validate_higher_perm_levels(doc)
    return doc


class TestAddRowVetting(unittest.TestCase):
    """Server decides what the new row is: item must be real, enabled and sellable."""

    def _resolve(self, meta):
        order = SimpleNamespace(name="SO-1", pos_profile=None, selling_price_list=None, customer="C")
        with patch.object(sales_orders.frappe.db, "get_value", return_value=meta):
            return sales_orders._resolve_managed_sales_order_item_pricing(order, "WIDGET", "Nos")

    def test_missing_item_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "does not exist"):
            self._resolve(None)

    def test_disabled_item_rejected(self):
        meta = {"item_name": "W", "stock_uom": "Nos", "has_variants": 0, "disabled": 1, "is_sales_item": 1}
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            self._resolve(meta)

    def test_non_sales_item_rejected(self):
        meta = {"item_name": "W", "stock_uom": "Nos", "has_variants": 0, "disabled": 0, "is_sales_item": 0}
        with self.assertRaisesRegex(RuntimeError, "not a sales item"):
            self._resolve(meta)


class TestPartnerAddRowPricing(tpp.Base):
    """The partner's new row is priced by the server from the customer's list."""

    def test_normaliser_ignores_a_tampered_client_rate_for_a_partner(self):
        order = SimpleNamespace(
            name="SO-1",
            company="TC",
            pos_profile=None,
            customer="CUST-A",
            currency="GBP",
            delivery_date=None,
            items=[],
        )
        incoming = [{"item_code": "WIDGET", "uom": "Nos", "qty": 1, "rate": 0.01}]
        with (
            patch.object(sales_orders, "is_partner_user", return_value=True),
            patch.object(
                sales_orders, "_resolve_managed_sales_order_item_pricing", return_value={"rate": 50.0}
            ) as priced,
            patch.object(sales_orders, "_get_managed_sales_order_ns_default_warehouse", return_value=None),
        ):
            rows = sales_orders._prepare_managed_sales_order_item_rows(order, incoming)
        priced.assert_called_once()
        self.assertEqual(rows[0]["rate"], 50.0)
        self.assertIsNone(rows[0]["delivery_date"])

    def test_tampered_rate_on_the_added_row_is_repriced_to_list(self):
        added = tpp.Row(
            idx=2, item_code="WIDGET", uom="Nos", conversion_factor=1, rate=0.01, price_list_rate=0.01
        )
        doc = tpp.Doc(
            customer="CUST-A",
            items=[added],
            selling_price_list="Standard Selling",
            ignore_pricing_rule=0,
            additional_discount_percentage=0,
            discount_amount=0,
            coupon_code="",
        )
        tpp.PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual((added.rate, added.price_list_rate), (50, 50))

    def test_discount_past_the_cap_on_the_added_row_is_rejected(self):
        added = tpp.Row(
            idx=2,
            item_code="WIDGET",
            uom="Nos",
            conversion_factor=1,
            rate=1,
            price_list_rate=1,
            discount_percentage=90,
        )
        doc = tpp.Doc(
            customer="CUST-A",
            items=[added],
            selling_price_list="x",
            ignore_pricing_rule=0,
            additional_discount_percentage=0,
            discount_amount=0,
            coupon_code="",
        )
        with self.assertRaisesRegex(Exception, "more than the"):
            tpp.PRICING.enforce_sales_order_pricing(doc)

    def test_unpriced_item_added_by_a_partner_is_rejected(self):
        tpp.STATE["prices"] = []
        added = tpp.Row(idx=2, item_code="WIDGET", uom="Nos", conversion_factor=1, rate=5, price_list_rate=5)
        doc = tpp.Doc(
            customer="CUST-A",
            items=[added],
            selling_price_list="x",
            ignore_pricing_rule=0,
            additional_discount_percentage=0,
            discount_amount=0,
            coupon_code="",
        )
        with self.assertRaisesRegex(Exception, "has no price on price list"):
            tpp.PRICING.enforce_sales_order_pricing(doc)


if __name__ == "__main__":
    unittest.main()
