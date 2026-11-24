"""Stub tests for delivery_eta.get_fixed_eta (run with plain python3).

frappe is the shared stub from test_sales_order_submit, extended per test. customer_due_dates'
real ``fixed_eta`` and ``eta_rules`` are loaded from their files, so the consistency test
compares the real rule with the real preview, not a copy of it.
"""

import importlib.util
import json
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_preview_delivery_window import FakePreviewSalesOrder
from test_sales_order_submit import sales_orders

API_DIR = Path(__file__).resolve().parent
CDD_SELLING = API_DIR.parents[3] / "customer_due_dates" / "customer_due_dates" / "selling"
FRAPPE = sys.modules["frappe"]
FRAPPE_UTILS = sys.modules["frappe.utils"]


class FakeValidationError(Exception):
    pass


class FakePermissionError(Exception):
    pass


class _dict(dict):
    __getattr__ = dict.get


def _parse_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Delivery Charges: name -> (order_type id, disabled, available_to)
CHARGES = {
    "FIXED-DDP": ("OT-DDP", 0, "Both"),
    "AGILE-FIXED": ("OT-DDP", 0, "Agile only"),
    "TFW-FIXED": ("OT-FOB", 0, "TFW only"),
    "DISABLED-FIXED": ("OT-DDP", 1, "Both"),
    "DHD": ("OT-DHD", 0, "Both"),
    "NO-TYPE": (None, 0, "Both"),
}
FIXED_ORDER_TYPES = {"OT-DDP": 1, "OT-FOB": 1, "OT-DHD": 0}
CUSTOMERS = {"CUST-A": "SP-A", "CUST-B": "SP-B"}
EXPRESS = {"SOFA": 1, "TABLE": 0, "PART-1": 1, "PART-2": 0, "PART-3": 1}

STATE = {}


class Base(unittest.TestCase):
    def setUp(self):
        STATE.clear()
        STATE.update(partner=False, offered={"FIXED-DDP", "AGILE-FIXED", "DHD", "NO-TYPE"}, item_queries=0)

        for name, exc in (("ValidationError", FakeValidationError), ("PermissionError", FakePermissionError)):
            self._patch(FRAPPE, name, exc, create=True)
        self._patch(FRAPPE, "_dict", _dict, create=True)
        self._patch(FRAPPE, "bold", lambda text: text, create=True)
        self._patch(FRAPPE, "parse_json", json.loads, create=True)
        self._patch(FRAPPE, "throw", self._throw)
        self._patch(FRAPPE, "get_all", self._get_all)
        self._patch(
            FRAPPE,
            "get_hooks",
            lambda key: ["x.scope"] if STATE["partner"] and key == "posa_user_scope" else [],
        )
        self._patch(
            FRAPPE, "get_attr", lambda path: lambda user: {"is_partner": True, "partners": ["SP-A"]}, create=True
        )
        self._patch(FRAPPE.db, "get_value", self._get_value)
        self._patch(FRAPPE.db, "exists", lambda doctype, name=None: doctype == "Delivery Charges" and name in CHARGES)
        self._patch(FRAPPE_UTILS, "getdate", _parse_date)
        self._patch(FRAPPE_UTILS, "nowdate", lambda: "2026-11-24")

        availability = types.ModuleType("customer_due_dates.selling.pos_availability")
        availability.is_available = lambda value, partner_mode: (value or "TFW only") in (
            ["Agile only", "Both"] if partner_mode else ["TFW only", "Both"]
        )
        dc_mod = types.ModuleType("posawesome.posawesome.doctype.delivery_charges.delivery_charges")
        dc_mod.get_applicable_delivery_charges = lambda company, profile, customer, *a, **k: [
            _dict(name=n) for n in STATE["offered"]
        ]
        modules = {
            # Other test files swap sys.modules["frappe"] at import; load against this one.
            "frappe": FRAPPE,
            "frappe.utils": FRAPPE_UTILS,
            "customer_due_dates.selling": types.ModuleType("customer_due_dates.selling"),
            "customer_due_dates.selling.pos_availability": availability,
            "posawesome.posawesome.doctype": types.ModuleType("posawesome.posawesome.doctype"),
            "posawesome.posawesome.doctype.delivery_charges": types.ModuleType(
                "posawesome.posawesome.doctype.delivery_charges"
            ),
            "posawesome.posawesome.doctype.delivery_charges.delivery_charges": dc_mod,
        }
        for name in ("customer_due_dates.selling", "posawesome.posawesome.doctype", "posawesome.posawesome.doctype.delivery_charges"):
            modules[name].__path__ = []
        # Fresh package shells: `from . import x` reads attributes of the package object, which
        # other test files leave behind pointing at their own copies of these modules.
        for name, path in (
            ("posawesome", API_DIR.parents[1]),
            ("posawesome.posawesome", API_DIR.parents[0]),
            ("posawesome.posawesome.api", API_DIR),
        ):
            package = types.ModuleType(name)
            package.__path__ = [str(path)] if name.endswith("api") else []
            modules[name] = package
        # patch.dict restores sys.modules afterwards, including the modules loaded below.
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.rules = _load("customer_due_dates.selling.eta_rules", CDD_SELLING / "eta_rules.py")
        self.fixed = _load("customer_due_dates.selling.fixed_eta", CDD_SELLING / "fixed_eta.py")
        self.charge_pricing = _load("posawesome.posawesome.api.charge_pricing", API_DIR / "charge_pricing.py")
        self.gate = _load("posawesome.posawesome.api.partner_gate", API_DIR / "partner_gate.py")
        self.eta = _load("posawesome.posawesome.api.delivery_eta", API_DIR / "delivery_eta.py")
        api = sys.modules["posawesome.posawesome.api"]
        api.charge_pricing, api.partner_gate = self.charge_pricing, self.gate
        self._patch(self.charge_pricing, "server_profile_context", lambda user=None: ("POS", "Co"))

    def _patch(self, target, attr, value, create=False):
        p = patch.object(target, attr, value, create=create)
        p.start()
        self.addCleanup(p.stop)

    @staticmethod
    def _throw(message, exc=Exception, **kwargs):
        raise exc(message)

    def _get_all(self, doctype, filters=None, fields=None, **kwargs):
        STATE["item_queries"] += 1
        return [_dict(name=c, agiletfw_express=EXPRESS.get(c, 0)) for c in filters["name"][1]]

    def _get_value(self, doctype, name, fieldname=None, as_dict=False, **kwargs):
        if doctype == "Order Type":
            return FIXED_ORDER_TYPES.get(name)
        if doctype == "Customer":
            return CUSTOMERS.get(name)
        if doctype == "Delivery Charges" and name in CHARGES:
            order_type, disabled, available_to = CHARGES[name]
            row = {
                "order_type": order_type,
                "disabled": disabled,
                "available_to": available_to,
                "price_list": None,
                "price_list_overrides_customer": 0,
            }
            if isinstance(fieldname, (list, tuple)):
                return _dict({f: row[f] for f in fieldname}) if as_dict else tuple(row[f] for f in fieldname)
            return row[fieldname]
        return None

    def call(self, **kw):
        kw.setdefault("items", [{"item_code": "SOFA", "qty": 1, "key": "a"}])
        return self.eta.get_fixed_eta(**kw)


class TestStaffPath(Base):
    def test_fixed_charge_returns_the_rule_dates(self):
        items = [
            {"item_code": "SOFA", "qty": 1, "key": "a"},
            {"item_code": "TABLE", "qty": 2, "key": "b"},
        ]
        result = self.call(delivery_charge="TFW-FIXED", items=items, transaction_date="2026-11-24")
        self.assertTrue(result["applies"])
        self.assertEqual(result["lines"], {"a": "2027-02-16", "b": "2027-03-16"})  # +12w, +16w
        self.assertEqual(result["overall_eta"], "2027-03-16")
        self.assertEqual(result["weeks"], {"a": 12, "b": 16})

    def test_items_may_be_json_and_date_defaults_to_today(self):
        result = self.call(delivery_charge="TFW-FIXED", items=json.dumps([{"item_code": "TABLE", "qty": 1}]))
        self.assertEqual(result["lines"], {1: "2027-03-16"})

    def test_kit_parts_are_quoted_together(self):
        items = [{"item_code": c, "qty": 1, "key": c, "kit_group_id": "K1"} for c in ("PART-1", "PART-2", "PART-3")]
        result = self.call(delivery_charge="TFW-FIXED", items=items)
        self.assertEqual(set(result["weeks"].values()), {16})

    def test_no_charge_or_charge_without_a_fixed_eta_does_not_apply(self):
        empty = {"applies": False, "lines": {}, "overall_eta": None, "weeks": {}}
        self.assertEqual(self.call(delivery_charge=None), empty)
        self.assertEqual(self.call(delivery_charge=""), empty)
        self.assertEqual(self.call(delivery_charge="NO-TYPE"), empty)
        # A DHD charge: its order type is not a fixed-ETA one, whatever DHD means elsewhere.
        self.assertEqual(self.call(delivery_charge="DHD", customer=None), empty)
        self.assertEqual(STATE["item_queries"], 0, "no item lookup when the rule does not apply")

    def test_empty_basket_does_not_apply(self):
        self.assertFalse(self.call(delivery_charge="TFW-FIXED", items=[])["applies"])
        self.assertFalse(self.call(delivery_charge="TFW-FIXED", items=None)["applies"])

    def test_staff_cannot_use_an_unavailable_or_unknown_charge(self):
        for charge in ("AGILE-FIXED", "DISABLED-FIXED", "MISSING"):
            with self.subTest(charge=charge), self.assertRaises(FakePermissionError):
                self.call(delivery_charge=charge)

    def test_one_batched_item_query(self):
        items = [{"item_code": c, "qty": 1} for c in ("SOFA", "TABLE", "PART-1", "PART-2", "SOFA")]
        self.call(delivery_charge="TFW-FIXED", items=items)
        self.assertEqual(STATE["item_queries"], 1)


class TestPartnerPath(Base):
    def setUp(self):
        super().setUp()
        STATE["partner"] = True

    def test_offered_charge_for_own_customer(self):
        result = self.call(customer="CUST-A", delivery_charge="AGILE-FIXED")
        self.assertTrue(result["applies"])
        self.assertEqual(result["overall_eta"], "2027-02-16")

    def test_charge_not_offered_to_partners_is_refused(self):
        # offered list is what get_applicable_delivery_charges returns; FIXED-DDP is not in it here.
        STATE["offered"] = {"DHD"}
        with self.assertRaises(FakePermissionError):
            self.call(customer="CUST-A", delivery_charge="AGILE-FIXED")

    def test_other_partners_customer_is_refused_before_any_lookup(self):
        for customer in ("CUST-B", "CUST-MISSING"):
            with self.subTest(customer=customer), self.assertRaises(FakePermissionError):
                self.call(customer=customer, delivery_charge="AGILE-FIXED")
        self.assertEqual(STATE["item_queries"], 0)

    def test_no_customer_still_needs_an_offered_charge(self):
        self.assertTrue(self.call(delivery_charge="AGILE-FIXED")["applies"])
        STATE["offered"] = set()
        with self.assertRaises(FakePermissionError):
            self.call(delivery_charge="AGILE-FIXED")

    def test_no_charge_for_a_partner_is_not_applicable(self):
        self.assertFalse(self.call(customer="CUST-A", delivery_charge=None)["applies"])


class TestValidation(Base):
    def test_bad_items_are_refused(self):
        too_many = [{"item_code": "SOFA", "qty": 1}] * (self.eta.MAX_ITEMS + 1)
        bad = [
            "not json",
            "{}",
            {"item_code": "SOFA"},
            42,
            ["SOFA"],
            [{"qty": 1}],
            [{"item_code": ""}],
            [{"item_code": ["SOFA"], "qty": 1}],
            [{"item_code": "SOFA", "qty": "many"}],
            [{"item_code": "SOFA", "qty": None}],
            [{"item_code": "SOFA", "qty": True}],
            [{"item_code": "SOFA", "qty": float("inf")}],
            [{"item_code": "SOFA", "qty": float("nan")}],
            [{"item_code": "SOFA", "qty": [1]}],
            [{"item_code": "SOFA", "qty": 1, "key": {"x": 1}}],
            [{"item_code": "SOFA", "qty": 1, "kit_group_id": ["K"]}],
            [{"item_code": "X" * 141, "qty": 1}],
            too_many,
        ]
        for items in bad:
            with self.subTest(items=str(items)[:60]), self.assertRaises(FakeValidationError):
                self.call(delivery_charge="TFW-FIXED", items=items)

    def test_limit_is_inclusive(self):
        items = [{"item_code": "SOFA", "qty": 1, "key": i} for i in range(self.eta.MAX_ITEMS)]
        self.assertEqual(len(self.call(delivery_charge="TFW-FIXED", items=items)["lines"]), self.eta.MAX_ITEMS)

    def test_invalid_date_customer_and_charge_types_are_refused(self):
        for kw in (
            {"transaction_date": "not a date"},
            {"transaction_date": "2026-13-45"},
            {"customer": ["CUST-A"]},
            {"delivery_charge": ["TFW-FIXED"]},
        ):
            with self.subTest(kw=kw), self.assertRaises(FakeValidationError):
                self.call(**{"delivery_charge": "TFW-FIXED", **kw})

    def test_validation_runs_before_the_no_charge_shortcut(self):
        with self.assertRaises(FakeValidationError):
            self.call(delivery_charge=None, items="not json")

    def test_it_never_writes(self):
        writes = []
        for attr in ("set_value", "commit", "sql"):
            self._patch(FRAPPE.db, attr, lambda *a, _n=attr, **k: writes.append(_n), create=True)
        self.call(delivery_charge="TFW-FIXED")
        self.assertEqual(writes, [])


class TestConsistencyWithPreview(Base):
    """get_fixed_eta and the quoted-delivery preview run the same rule.

    cdd's ``apply_fixed_quoted_dates`` (called at the end of submit-time allocation) sets each
    line's ``quoted_date`` from ``compute_for_doc``; ``eta_for_lines`` uses the same
    ``compute_for_rows``. They are equal when the order's ``transaction_date`` is the date given
    to get_fixed_eta and the order's charge is the one given. The preview's header
    ``latest_quoted_date`` is a roll-up of line dates that cdd's snapshot does elsewhere; here the
    stub allocator sets it from the lines the same way (max), which is that roll-up.
    """

    ITEMS = [
        ("SOFA", "row-a", None),
        ("TABLE", "row-b", None),
        ("PART-1", "row-c", "K1"),
        ("PART-2", "row-d", "K1"),
        ("PART-3", "row-e", "K1"),
    ]

    def _run_preview(self, charge, transaction_date):
        doc = FakePreviewSalesOrder()
        doc.items = [
            SimpleNamespace(
                name=f"soi-{i}", idx=i, posa_row_id=row_id, item_code=code, item_name=code, qty=1,
                quoted_date=None, kit_group_id=kit,
            )
            for i, (code, row_id, kit) in enumerate(self.ITEMS, start=1)
        ]
        doc.posa_delivery_charges = charge
        doc.agiletfw_order_type = None
        doc.transaction_date = transaction_date

        def get(key, default=None):
            return getattr(doc, key, default)

        doc.get = get
        for row in doc.items:
            row.get = lambda key, default=None, _r=row: getattr(_r, key, default)

        def auto_allocate(d):
            self.fixed.apply_fixed_quoted_dates(d)
            d.latest_quoted_date = max(row.quoted_date for row in d.items)

        cdd_override = types.ModuleType("customer_due_dates.kit_items.overrides.sales_order")
        cdd_override.auto_allocate_on_so_submit = auto_allocate
        rfs = types.ModuleType("customer_due_dates.utils.rfs_customer")
        rfs.apply_sales_order_naming_series = lambda d, force=False: None
        rfs.is_rfs_customer = lambda customer: False
        due_dates = types.ModuleType("customer_due_dates.item_due_dates.prealloc.due_dates")
        due_dates._is_ns_item = lambda code: False
        alloc = types.ModuleType("customer_due_dates.item_due_dates.prealloc.so_alloc_fields")
        alloc._preallocated_outstanding_for_soi = lambda name: 0
        alloc._reserved_for_soi = lambda name: 0

        patches = [
            patch.dict(
                sys.modules,
                {
                    "customer_due_dates.kit_items.overrides.sales_order": cdd_override,
                    "customer_due_dates.utils.rfs_customer": rfs,
                    "customer_due_dates.item_due_dates.prealloc.so_alloc_fields": alloc,
                    "customer_due_dates.item_due_dates.prealloc.due_dates": due_dates,
                },
            ),
            patch.object(sales_orders.frappe, "get_doc", return_value=doc),
            patch.object(sales_orders.frappe, "clear_document_cache", create=True),
        ]
        for helper in (
            "_map_delivery_dates", "_apply_ns_default_warehouse", "_force_peterborough_store_collection",
            "_sync_shopify_notes_from_posa", "_apply_kit_meta_fields", "_apply_delivery_charges_tax_row",
        ):
            patches.append(patch.object(sales_orders, helper))
        sales_orders.frappe.db._disable_transaction_control = 0
        sales_orders.frappe.db.commit = lambda *a, **k: None
        sales_orders.frappe.db.rollback = lambda *a, **k: None
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return sales_orders.preview_quoted_delivery_window(
            json.dumps({"doctype": "Sales Order", "customer": "C-1", "items": [], "posa_delivery_charges": charge})
        )

    def _eta(self, charge, transaction_date):
        items = [{"item_code": c, "qty": 1, "key": row_id, "kit_group_id": kit} for c, row_id, kit in self.ITEMS]
        return self.call(delivery_charge=charge, items=items, transaction_date=transaction_date)

    def test_line_dates_and_overall_equal_the_preview(self):
        preview = self._run_preview("TFW-FIXED", "2026-11-24")
        eta = self._eta("TFW-FIXED", "2026-11-24")
        self.assertTrue(eta["applies"])
        self.assertEqual({l["posa_row_id"]: l["quoted_date"] for l in preview["lines"]}, eta["lines"])
        self.assertEqual(preview["latest_quoted_date"], eta["overall_eta"])
        # Not vacuous: express, non-express and a kit that is not wholly express all appear.
        self.assertEqual(sorted(set(eta["weeks"].values())), [12, 16])

    def test_a_backdated_order_differs_only_by_transaction_date(self):
        # The order is quoted from its own transaction_date; get_fixed_eta defaults to today.
        # Passing the same date makes them equal; omitting it does not, by design.
        preview = self._run_preview("TFW-FIXED", "2026-11-10")
        eta_same = self._eta("TFW-FIXED", "2026-11-10")
        self.assertEqual({l["posa_row_id"]: l["quoted_date"] for l in preview["lines"]}, eta_same["lines"])
        self.assertNotEqual(self._eta("TFW-FIXED", None)["lines"], eta_same["lines"])


if __name__ == "__main__":
    unittest.main()
