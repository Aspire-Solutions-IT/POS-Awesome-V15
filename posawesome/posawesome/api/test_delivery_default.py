"""get_applicable_delivery_charges picks its default through customer_due_dates.mark_default.

Plain-python test (stubs, no bench): python3 -m unittest posawesome/posawesome/api/test_delivery_default.py
"""

import importlib.util
import pathlib
import sys
import types
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / "doctype" / "delivery_charges" / "delivery_charges.py"


class _dict(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


STATE = {}
NAMES = [
    "frappe",
    "frappe.utils",
    "frappe.model",
    "frappe.model.document",
    "customer_due_dates",
    "customer_due_dates.selling",
    "customer_due_dates.selling.pos_availability",
    "posawesome",
    "posawesome.posawesome",
    "posawesome.posawesome.api",
    "posawesome.posawesome.api.charge_pricing",
]


SAVED = {}


def _restore():
    # The function imports lazily at call time, so stubs stay installed until tearDown.
    for n, m in SAVED.items():
        if m is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = m
    SAVED.clear()


def _load(with_cdd=True, with_mark_default=True):
    _restore()
    SAVED.update({n: sys.modules.get(n) for n in NAMES})
    for n in NAMES:
        sys.modules.pop(n, None)

    frappe = types.ModuleType("frappe")
    frappe._ = lambda t: t
    frappe.throw = lambda m: (_ for _ in ()).throw(Exception(m))

    def get_all(doctype, filters=None, fields=None, pluck=None):
        if doctype == "Delivery Charges":
            return [_dict(r) for r in STATE["charges"]]
        if doctype == "Delivery Charges POS Profile":
            return []
        return []

    frappe.get_all = get_all
    frappe.get_cached_value = lambda *a: None
    utils = types.ModuleType("frappe.utils")
    utils.cint = lambda v=0: int(v or 0)
    model = types.ModuleType("frappe.model")
    document = types.ModuleType("frappe.model.document")
    document.Document = object
    frappe.utils = utils

    charge_pricing = types.ModuleType("posawesome.posawesome.api.charge_pricing")
    charge_pricing._is_partner_mode = lambda: STATE["partner"]
    charge_pricing.filter_available = lambda charges: [c for c in charges if c.name not in STATE["hidden"]]

    mods = {
        "frappe": frappe,
        "frappe.utils": utils,
        "frappe.model": model,
        "frappe.model.document": document,
        "posawesome": types.ModuleType("posawesome"),
        "posawesome.posawesome": types.ModuleType("posawesome.posawesome"),
        "posawesome.posawesome.api": types.ModuleType("posawesome.posawesome.api"),
        "posawesome.posawesome.api.charge_pricing": charge_pricing,
    }
    if with_cdd:
        mods["customer_due_dates"] = types.ModuleType("customer_due_dates")
        mods["customer_due_dates.selling"] = types.ModuleType("customer_due_dates.selling")
        pa = types.ModuleType("customer_due_dates.selling.pos_availability")
        if with_mark_default:

            def mark_default(charges, partner_mode=None):
                STATE["mark_default_args"] = (list(charges), partner_mode)
                for c in charges:
                    c["is_default"] = 1 if c.name == STATE.get("default") else 0
                return charges

            pa.mark_default = mark_default
        mods["customer_due_dates.selling.pos_availability"] = pa
    else:
        # A None entry makes the import raise ImportError.
        mods["customer_due_dates.selling.pos_availability"] = None
    sys.modules.update(mods)
    spec = importlib.util.spec_from_file_location("dc_under_test", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _charges():
    return [
        _dict(name="A", default_rate=5, profiles_list=None, is_default=1),
        _dict(name="B", default_rate=7, profiles_list=None, is_default=0),
    ]


class TestDeliveryDefault(unittest.TestCase):
    def setUp(self):
        STATE.clear()
        STATE.update(charges=_charges(), partner=False, hidden=set(), default=None)

    def tearDown(self):
        _restore()

    def _call(self, module):
        return module.get_applicable_delivery_charges("Co")

    def test_partner_flag_is_passed_through(self):
        module = _load()
        for partner in (True, False):
            STATE["partner"] = partner
            self._call(module)
            self.assertEqual(STATE["mark_default_args"][1], partner)

    def test_default_comes_from_mark_default_not_old_checkbox(self):
        STATE["default"] = "B"
        result = self._call(_load())
        self.assertEqual({c.name: c.is_default for c in result}, {"A": 0, "B": 1})

    def test_hidden_charge_is_not_passed_to_mark_default(self):
        STATE["hidden"] = {"A"}
        STATE["default"] = "A"
        result = self._call(_load())
        self.assertEqual([c.name for c in result], ["B"])
        self.assertEqual([c.name for c in STATE["mark_default_args"][0]], ["B"])
        self.assertEqual(result[0].is_default, 0)

    def test_no_default_when_none_matches(self):
        result = self._call(_load())
        self.assertTrue(all(c.is_default == 0 for c in result))

    def test_import_error_falls_back_to_old_flag(self):
        for module in (_load(with_cdd=False), _load(with_mark_default=False)):
            result = self._call(module)
            self.assertEqual({c.name: c.is_default for c in result}, {"A": 1, "B": 0})

    def test_fallback_without_any_flag_column_sets_zero(self):
        STATE["charges"] = [_dict(name="A", default_rate=5, profiles_list=None)]
        result = self._call(_load(with_cdd=False))
        self.assertEqual(result[0].is_default, 0)


if __name__ == "__main__":
    unittest.main()
