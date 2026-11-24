"""Stub test: ``get_items`` with the server cache on keys its cache by the delivery charge.

The charge decides each row's ``fixed_eta_weeks`` (and a locked charge's price list), so a result
cached for one charge must never be served for another. Run with plain python3.
"""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

API_DIR = Path(__file__).resolve().parent
PKG = "posawesome.posawesome.api"


class _dict(dict):
    __getattr__ = dict.get


def _load():
    frappe = types.ModuleType("frappe")
    frappe._ = lambda text: text
    frappe._dict = _dict
    frappe.as_json = json.dumps
    frappe.form_dict = _dict()
    frappe.db = types.SimpleNamespace(has_column=lambda *a: False)
    frappe.get_all = lambda doctype, **kw: [_dict(name="SOFA", item_code="SOFA", item_name="Sofa")]
    frappe.throw = lambda msg, *a: (_ for _ in ()).throw(Exception(msg))

    def whitelist(*args, **kwargs):
        return args[0] if args and callable(args[0]) else (lambda fn: fn)

    frappe.whitelist = whitelist
    frappe.validate_and_sanitize_search_inputs = lambda fn: fn
    utils = types.ModuleType("frappe.utils")
    utils.cint = lambda v=0: int(v or 0)
    utils.cstr = lambda v: "" if v is None else str(v)
    utils.get_datetime = lambda v: v
    caching = types.ModuleType("frappe.utils.caching")
    store = {}

    def redis_cache(ttl=None):
        def wrap(fn):
            def cached(*args):
                if args not in store:
                    store[args] = fn(*args)
                return store[args]

            return cached

        return wrap

    caching.redis_cache = redis_cache

    calls = []

    def get_items_details(pos_profile, items_data, price_list=None, customer=None, delivery_charge=None):
        calls.append(delivery_charge)
        return [
            {"item_code": i["item_code"], "price_list_rate": 1, **({"fixed_eta_weeks": 12} if delivery_charge else {})}
            for i in json.loads(items_data)
        ]

    def stub(name, **attrs):
        module = types.ModuleType(name)
        module.__dict__.update(attrs)
        return module

    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(API_DIR)]
    fakes = {
        "frappe": frappe,
        "frappe.utils": utils,
        "frappe.utils.caching": caching,
        "posawesome": types.ModuleType("posawesome"),
        "posawesome.posawesome": types.ModuleType("posawesome.posawesome"),
        PKG: pkg,
        f"{PKG}.partner_pricing": stub(
            f"{PKG}.partner_pricing", exclusion_field=lambda: None, is_unpriced=lambda item, detail: False
        ),
        f"{PKG}.partner_gate": stub(f"{PKG}.partner_gate", is_partner_user=lambda: False),
        f"{PKG}.item_fetchers": stub(f"{PKG}.item_fetchers", ItemDetailAggregator=object),
        f"{PKG}.utils": stub(
            f"{PKG}.utils",
            HAS_VARIANTS_EXCLUSION={},
            expand_item_groups=lambda groups: groups,
            get_active_pos_profile=lambda: None,
            get_item_groups=lambda name: [],
            _ensure_pos_profile=lambda profile: (json.loads(profile), profile),
            log_perf_event=lambda *a, **k: None,
        ),
        f"{PKG}.item_processing": types.ModuleType(f"{PKG}.item_processing"),
        f"{PKG}.item_processing.barcode": stub(
            f"{PKG}.item_processing.barcode", search_serial_or_batch_or_barcode_number=lambda *a: {}
        ),
        f"{PKG}.item_processing.details": stub(f"{PKG}.item_processing.details", get_items_details=get_items_details),
    }
    fakes[f"{PKG}.item_processing"].__path__ = []
    with mock.patch.dict(sys.modules, fakes):
        spec = importlib.util.spec_from_file_location(
            f"{PKG}.item_processing.search", API_DIR / "item_processing" / "search.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, frappe, store, calls


class TestGetItemsCacheKeyedByCharge(unittest.TestCase):
    PROFILE = json.dumps({"name": "POS", "posa_use_server_cache": 1, "selling_price_list": "Standard Selling"})

    def setUp(self):
        self.search, self.frappe, self.store, self.calls = _load()

    def _rows(self, charge):
        self.frappe.form_dict.clear()
        if charge:
            self.frappe.form_dict["delivery_charge"] = charge
        return self.search.get_items(self.PROFILE, price_list="Standard Selling")

    def test_switching_the_charge_does_not_leak_or_drop_the_field(self):
        self.assertNotIn("fixed_eta_weeks", self._rows(None)[0])
        self.assertEqual(self._rows("DDP")[0]["fixed_eta_weeks"], 12)  # not the cached plain rows
        self.assertNotIn("fixed_eta_weeks", self._rows(None)[0])  # not the cached DDP rows
        self.assertEqual(self._rows("DDP")[0]["fixed_eta_weeks"], 12)

    def test_the_charge_is_passed_explicitly_and_a_repeat_is_a_cache_hit(self):
        self._rows("DDP")
        self._rows("DDP")
        self._rows(None)
        self.assertEqual(self.calls, ["DDP", ""], "one lookup per distinct charge; no charge is an explicit ''")


if __name__ == "__main__":
    unittest.main()
