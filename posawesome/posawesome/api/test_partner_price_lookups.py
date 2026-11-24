"""get_price_for_uom for partners and staff (AP-1): a partner is priced from the list the
customer and the order's charge resolve to (never the browser's price_list), and staff are
unchanged."""

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

    def get_uom_rate(item_code, uom, customer, delivery_charge=None):
        calls["visible"].append((item_code, uom, customer, delivery_charge))
        return visible_price

    partner_pricing.get_uom_rate = get_uom_rate

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
    def run_case(self, partner, price_list, **kw):
        module, calls = _load(partner, set(), **kw)
        try:
            return module.get_price_for_uom("ITEM-1", price_list, "Nos", "CUST-A", "Free delivery"), calls
        finally:
            module._restore()

    def test_partner_is_priced_from_the_customer_and_charge_not_the_browsers_list(self):
        for browser_list in ("PL-OWN", "Standard Buying", "PL-OTHER-CUSTOMER", ""):
            price, calls = self.run_case(True, browser_list)
            self.assertEqual(price, "9.5", browser_list)
            self.assertEqual(calls["visible"], [("ITEM-1", "Nos", "CUST-A", "Free delivery")])
            self.assertEqual(calls["db"], [], "no raw Item Price read for a partner")

    def test_staff_are_unchanged_and_may_use_any_list(self):
        price, calls = self.run_case(False, "Standard Buying")
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
        module, _calls = _load(False, set())
        try:
            self.assertIsNone(module.get_price_for_uom("ITEM-1", "", "Nos"))
            self.assertIsNone(module.get_price_for_uom("", "PL", "Nos"))
        finally:
            module._restore()


if __name__ == "__main__":
    unittest.main()
