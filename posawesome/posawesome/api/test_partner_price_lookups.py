"""get_price_for_uom for partners and staff (AP-1 H2): a partner is refused any price list
they cannot price from, and never reads another customer's Item Price row."""

import importlib.util
import pathlib
import sys
import types
import unittest

PRICE_PATH = pathlib.Path(__file__).resolve().parent / "item_processing" / "price.py"


class FakePermissionError(Exception):
    pass


def _load(partner, allowed, visible_price="9.5", staff_price="1.25"):
    calls = {"db": [], "visible": []}

    frappe = types.ModuleType("frappe")
    frappe.PermissionError = FakePermissionError
    frappe._ = lambda text: text
    frappe.whitelist = lambda *a, **k: (lambda fn: fn)

    def throw(msg, exc=Exception):
        raise exc(msg)

    frappe.throw = throw
    frappe.db = types.SimpleNamespace(
        get_value=lambda doctype, filters, field: calls["db"].append((doctype, filters, field)) or staff_price
    )
    utils = types.ModuleType("frappe.utils")
    utils.flt = float
    frappe.utils = utils

    barcode = types.ModuleType("posawesome.posawesome.api.item_processing.barcode")
    barcode._parse_scale_barcode_data = lambda barcode: None

    partner_pricing = types.ModuleType("posawesome.posawesome.api.partner_pricing")
    partner_pricing.is_partner_user = lambda: partner

    def get_visible_item_price(item_code, price_list, uom=None, currency=None):
        calls["visible"].append((item_code, price_list, uom))
        return visible_price

    partner_pricing.get_visible_item_price = get_visible_item_price

    gate = types.ModuleType("posawesome.posawesome.api.partner_gate")
    gate.get_scope = lambda user=None: {"is_partner": partner, "partners": ["SP-A"]}
    gate.allowed_price_lists = lambda partners: set(allowed)

    api = types.ModuleType("posawesome.posawesome.api")
    api.partner_pricing = partner_pricing
    api.__path__ = []

    stubs = {
        "frappe": frappe,
        "frappe.utils": utils,
        "posawesome": types.ModuleType("posawesome"),
        "posawesome.posawesome": types.ModuleType("posawesome.posawesome"),
        "posawesome.posawesome.api": api,
        "posawesome.posawesome.api.partner_pricing": partner_pricing,
        "posawesome.posawesome.api.partner_gate": gate,
        "posawesome.posawesome.api.item_processing": types.ModuleType(
            "posawesome.posawesome.api.item_processing"
        ),
        "posawesome.posawesome.api.item_processing.barcode": barcode,
    }
    saved = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location("price_under_test", PRICE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        # The imports inside get_price_for_uom run at call time, so keep the stubs in
        # place until the caller is done.
        module._restore = lambda: [
            sys.modules.pop(n, None) if old is None else sys.modules.__setitem__(n, old)
            for n, old in saved.items()
        ]
    except Exception:
        for n, old in saved.items():
            if old is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = old
        raise
    return module, calls


class TestGetPriceForUom(unittest.TestCase):
    def run_case(self, partner, allowed, price_list, **kw):
        module, calls = _load(partner, allowed, **kw)
        try:
            return module.get_price_for_uom("ITEM-1", price_list, "Nos"), calls
        finally:
            module._restore()

    def test_partner_own_list_works_and_uses_the_visible_price_lookup(self):
        price, calls = self.run_case(True, {"PL-OWN"}, "PL-OWN")
        self.assertEqual(price, "9.5")
        self.assertEqual(calls["visible"], [("ITEM-1", "PL-OWN", "Nos")])
        self.assertEqual(calls["db"], [], "no raw Item Price read for a partner")

    def test_partner_buying_or_foreign_list_is_refused_before_any_read(self):
        for price_list in ("Standard Buying", "PL-OTHER-CUSTOMER"):
            module, calls = _load(True, {"PL-OWN"})
            try:
                with self.assertRaises(FakePermissionError, msg=price_list):
                    module.get_price_for_uom("ITEM-1", price_list, "Nos")
            finally:
                module._restore()
            self.assertEqual(calls["db"], [])
            self.assertEqual(calls["visible"], [])

    def test_staff_are_unchanged_and_may_use_any_list(self):
        price, calls = self.run_case(False, set(), "Standard Buying")
        self.assertEqual(price, "1.25")
        self.assertEqual(
            calls["db"],
            [
                (
                    "Item Price",
                    {"item_code": "ITEM-1", "price_list": "Standard Buying", "uom": "Nos"},
                    "price_list_rate",
                )
            ],
        )
        self.assertEqual(calls["visible"], [])

    def test_missing_arguments_still_return_nothing(self):
        module, _calls = _load(True, set())
        try:
            self.assertIsNone(module.get_price_for_uom("ITEM-1", "", "Nos"))
        finally:
            module._restore()


if __name__ == "__main__":
    unittest.main()
