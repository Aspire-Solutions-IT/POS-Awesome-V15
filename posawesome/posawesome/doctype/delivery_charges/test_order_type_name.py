"""Stub test for _with_order_type_name (run with plain python3; frappe is faked)."""

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock

PATH = pathlib.Path(__file__).resolve().parent / "delivery_charges.py"


class _Doc:
    pass


def _load(order_types):
    frappe = types.ModuleType("frappe")
    frappe._ = lambda s: s
    frappe.get_all = mock.Mock(return_value=order_types)
    model = types.ModuleType("frappe.model")
    document = types.ModuleType("frappe.model.document")
    document.Document = _Doc
    utils = types.ModuleType("frappe.utils")
    utils.cint = int
    frappe.utils = utils
    fakes = {
        "frappe": frappe,
        "frappe.model": model,
        "frappe.model.document": document,
        "frappe.utils": utils,
    }
    with mock.patch.dict(sys.modules, fakes):
        spec = importlib.util.spec_from_file_location("dc_under_test", PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, frappe


class TestOrderTypeName(unittest.TestCase):
    def test_adds_name_from_order_type_id(self):
        class Row:
            def __init__(self, name, order_type_name):
                self.name, self.order_type_name = name, order_type_name

        module, frappe = _load([Row("OT-0001", "DHD")])
        charges = [{"name": "Home", "order_type": "OT-0001"}, {"name": "Collect", "order_type": None}]
        out = module._with_order_type_name(charges)
        self.assertEqual(out[0]["order_type_name"], "DHD")
        self.assertEqual(out[1]["order_type_name"], "")
        frappe.get_all.assert_called_once()

    def test_no_order_types_means_no_query(self):
        module, frappe = _load([])
        out = module._with_order_type_name([{"name": "A"}])
        self.assertEqual(out[0]["order_type_name"], "")
        frappe.get_all.assert_not_called()


if __name__ == "__main__":
    unittest.main()
