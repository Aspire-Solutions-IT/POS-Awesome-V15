import json
import unittest
from unittest.mock import patch

from posawesome.posawesome.api.item_processing import search

PROFILE = json.dumps({"name": "_Test Advanced Search Profile", "selling_price_list": "Standard Selling"})


class TestSearchItemsByCode(unittest.TestCase):
    def _captured_filters(self, **kwargs):
        with patch.object(search, "_run_item_query", return_value=[]) as run_query:
            search.search_items_by_code(PROFILE, item_groups=[], **kwargs)
        plan = run_query.call_args.args[3]
        return plan.filters

    def test_default_matches_code_substring(self):
        filters = self._captured_filters(search_value="10_BET")
        self.assertEqual(filters["item_code"], ["like", "%10\\_BET%"])

    def test_exact_matches_code_only(self):
        filters = self._captured_filters(search_value="CO-10BET", exact=1)
        self.assertEqual(filters["item_code"], "CO-10BET")

    def test_exact_accepts_string_flag(self):
        filters = self._captured_filters(search_value="CO-10BET", exact="1")
        self.assertEqual(filters["item_code"], "CO-10BET")


class TestItemAdvancedSearchQuery(unittest.TestCase):
    PREFIX = "_TADVSRCH"

    def setUp(self):
        import frappe

        if not search._item_has_custom_exclude_from_pos():
            self.skipTest("Item.custom_exclude_from_pos is not installed on this site")
        self._previous_user = frappe.session.user
        frappe.set_user("Administrator")
        for code, excluded in ((f"{self.PREFIX}-KEEP", 0), (f"{self.PREFIX}-HIDE", 1)):
            frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": code,
                    "item_name": code,
                    "item_group": "All Item Groups",
                    "stock_uom": "Nos",
                    "is_sales_item": 1,
                    "is_stock_item": 0,
                    "custom_exclude_from_pos": excluded,
                }
            ).insert(ignore_permissions=True, ignore_mandatory=True)

    def tearDown(self):
        import frappe

        frappe.db.rollback()
        frappe.set_user(getattr(self, "_previous_user", "Guest"))

    def _codes(self, filters):
        rows = search.item_advanced_search_query("Item", self.PREFIX, "name", 0, 20, filters)
        return {row[0] for row in rows}

    # No caller filters here: test_agile.localhost puts most Item flags (is_sales_item,
    # has_variants, ...) above permlevel 0 with no role granted those levels, so
    # filtering on them raises PermissionError. custom_exclude_from_pos is level 0.
    def test_excludes_items_hidden_from_pos(self):
        codes = self._codes({})
        self.assertEqual(codes, {f"{self.PREFIX}-KEEP"})

    def test_accepts_json_filters(self):
        codes = self._codes(json.dumps({}))
        self.assertEqual(codes, {f"{self.PREFIX}-KEEP"})
