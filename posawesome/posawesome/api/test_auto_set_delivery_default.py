"""auto_set_delivery_charges prefers the flagged default charge.

Plain-python test (stubs, no bench): python3 posawesome/posawesome/api/test_auto_set_delivery_default.py
"""

import importlib.util
import pathlib
import sys
import types
import unittest

PATH = pathlib.Path(__file__).resolve().parent / "invoice.py"

NAMES = [
    "frappe",
    "frappe.model",
    "frappe.model.mapper",
    "frappe.utils",
    "posawesome",
    "posawesome.posawesome",
    "posawesome.posawesome.api",
    "posawesome.posawesome.api.utilities",
    "posawesome.posawesome.api.payments",
    "posawesome.posawesome.doctype",
    "posawesome.posawesome.doctype.delivery_charges",
    "posawesome.posawesome.doctype.delivery_charges.delivery_charges",
    "posawesome.posawesome.doctype.pos_coupon",
    "posawesome.posawesome.doctype.pos_coupon.pos_coupon",
]
SAVED = {}
STATE = {}


class _dict(dict):
    __getattr__ = dict.get

    def __setattr__(self, key, value):
        self[key] = value


def _load():
    SAVED.update({n: sys.modules.get(n) for n in NAMES})
    mods = {n: types.ModuleType(n) for n in NAMES}
    mods["frappe"]._ = lambda t: t
    mods["frappe"].get_cached_value = lambda *a: STATE["auto_set"]
    mods["frappe.model.mapper"].get_mapped_doc = lambda *a, **k: None
    mods["frappe.utils"].add_days = lambda *a: None
    mods["frappe.utils"].flt = float
    mods["posawesome.posawesome.api.utilities"].get_company_domain = lambda c: None
    mods["posawesome.posawesome.api.payments"].get_posawesome_credit_redeem_remark = lambda *a: ""
    mods["posawesome.posawesome.doctype.delivery_charges.delivery_charges"].get_applicable_delivery_charges = (
        lambda *a, **k: [_dict(c) for c in STATE["charges"]]
    )
    mods["posawesome.posawesome.doctype.pos_coupon.pos_coupon"].update_coupon_code_count = lambda *a: None
    sys.modules.update(mods)
    spec = importlib.util.spec_from_file_location("invoice_under_test", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _restore():
    for n, m in SAVED.items():
        if m is None:
            sys.modules.pop(n, None)
        else:
            sys.modules[n] = m
    SAVED.clear()


def _doc(**kw):
    values = dict(
        pos_profile="P",
        company="Co",
        customer="C",
        shipping_address_name=None,
        posa_delivery_charges=None,
        posa_delivery_charges_rate=None,
    )
    values.update(kw)
    return _dict(values)


class TestAutoSetDeliveryDefault(unittest.TestCase):
    def setUp(self):
        STATE.clear()
        STATE.update(
            auto_set=1,
            charges=[
                dict(name="A", rate=5, is_default=0),
                dict(name="B", rate=7, is_default=1),
                dict(name="C", rate=9, is_default=0),
            ],
        )
        self.module = _load()

    def tearDown(self):
        _restore()

    def test_flagged_default_is_chosen_over_first_row(self):
        doc = _doc()
        self.module.auto_set_delivery_charges(doc)
        self.assertEqual((doc.posa_delivery_charges, doc.posa_delivery_charges_rate), ("B", 7))

    def test_first_row_when_nothing_is_flagged(self):
        for c in STATE["charges"]:
            c["is_default"] = 0
        doc = _doc()
        self.module.auto_set_delivery_charges(doc)
        self.assertEqual((doc.posa_delivery_charges, doc.posa_delivery_charges_rate), ("A", 5))

    def test_explicit_charge_is_never_replaced(self):
        doc = _doc(posa_delivery_charges="C", posa_delivery_charges_rate=9)
        self.module.auto_set_delivery_charges(doc)
        self.assertEqual((doc.posa_delivery_charges, doc.posa_delivery_charges_rate), ("C", 9))

    def test_no_charges_clears_the_fields(self):
        STATE["charges"] = []
        doc = _doc()
        self.module.auto_set_delivery_charges(doc)
        self.assertIsNone(doc.posa_delivery_charges)

    def test_does_nothing_when_auto_set_is_off(self):
        STATE["auto_set"] = 0
        doc = _doc()
        self.module.auto_set_delivery_charges(doc)
        self.assertIsNone(doc.posa_delivery_charges)


if __name__ == "__main__":
    unittest.main()
