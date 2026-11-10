from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch

import frappe

from posawesome.posawesome.api.stainguard import validate_pos_stainguard


class TestPosStainguard(TestCase):
    def setUp(self):
        self.payload = {
            "posa_stainguard_enabled": 1,
            "pos_profile": "Main",
            "customer": "Customer",
            "discount_amount": 100,
            "items": [
                {"item_code": "SOFA", "qty": 1, "rate": 1000},
                {"item_code": "SG-1", "item_name": "Cover", "qty": 1, "rate": 40, "uom": "Nos"},
            ],
        }
        self.profile = frappe._dict(name="Main", posa_enable_stainguard=1)
        self.profile.check_permission = lambda permission: None
        patches = [
            patch("posawesome.posawesome.api.stainguard.frappe.db.has_column", return_value=True),
            patch("posawesome.posawesome.api.stainguard.frappe.get_all", return_value=["SG-1"]),
            patch("posawesome.posawesome.api.stainguard.frappe.get_cached_doc", return_value=self.profile),
            patch("customer_due_dates.staingard.pos.find_offer", return_value={"item_code": "SG-1"}),
            patch("posawesome.posawesome.api.item_processing.search.search_items_by_code", return_value=[
                {"item_code": "SG-1", "item_name": "Cover", "rate": 40, "stock_uom": "Nos"},
            ]),
            patch("posawesome.posawesome.api.stainguard.frappe.throw", side_effect=frappe.ValidationError),
            patch("posawesome.posawesome.api.stainguard._", side_effect=lambda text: text),
            patch("posawesome.posawesome.api.stainguard.frappe.get_system_settings", return_value="Banker's Rounding"),
        ]
        self.mocks = [self.enterContext(patcher) for patcher in patches]

    def test_accepts_checkbox_cover_and_excludes_cover_from_band_value(self):
        validate_pos_stainguard(self.payload)
        self.mocks[3].assert_called_once_with(900)
        self.assertNotIn("posa_stainguard_enabled", self.payload)

    def test_rejects_manual_add_when_unticked(self):
        self.payload["posa_stainguard_enabled"] = 0
        with self.assertRaises(frappe.ValidationError):
            validate_pos_stainguard(self.payload)

    def test_rejects_missing_cover_when_ticked(self):
        self.payload["items"].pop()
        with self.assertRaises(frappe.ValidationError):
            validate_pos_stainguard(self.payload)

    def test_rejects_duplicate_cover(self):
        self.payload["items"].append(deepcopy(self.payload["items"][-1]))
        with self.assertRaises(frappe.ValidationError):
            validate_pos_stainguard(self.payload)

    def test_rejects_manual_edits(self):
        changes = [
            {"qty": 2}, {"rate": 1}, {"uom": "Box"}, {"discount_percentage": 10},
            {"discount_amount": 5}, {"name_overridden": 1}, {"item_name": "Edited"},
        ]
        for change in changes:
            with self.subTest(change=change):
                payload = deepcopy(self.payload)
                payload["items"][-1].update(change)
                with self.assertRaises(frappe.ValidationError):
                    validate_pos_stainguard(payload)

    def test_rejects_wrong_band(self):
        self.mocks[3].return_value = {"item_code": "SG-2"}
        with self.assertRaises(frappe.ValidationError):
            validate_pos_stainguard(self.payload)

    def test_rejects_disabled_profile(self):
        self.profile.posa_enable_stainguard = 0
        with self.assertRaises(frappe.ValidationError):
            validate_pos_stainguard(self.payload)

    def test_allows_no_cover_when_no_band_exists(self):
        self.mocks[3].return_value = None
        self.payload["items"].pop()
        validate_pos_stainguard(self.payload)

    def test_allows_normal_baskets_and_installations_without_stainguard(self):
        self.payload["items"].pop()
        self.payload["posa_stainguard_enabled"] = 0
        validate_pos_stainguard(self.payload)
        self.mocks[0].return_value = False
        validate_pos_stainguard(self.payload)
