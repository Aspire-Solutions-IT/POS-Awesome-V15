"""Stub tests for order_address.create_order_address (run with plain python3).

frappe, charge_pricing, partner_gate and email_validation are faked, so no site is needed.
"""

import importlib.util
import pathlib
import sys
import types
import unittest
from unittest import mock

API_DIR = pathlib.Path(__file__).resolve().parent
PKG = "posawesome.posawesome.api"


class FakeValidationError(Exception):
    pass


class FakePermissionError(Exception):
    pass


class FakeDoesNotExistError(Exception):
    pass


class _dict(dict):
    __getattr__ = dict.get


# Reset per test.
STATE = {}


def _reset():
    STATE.clear()
    STATE.update(
        partners=["SP-A"],  # None = staff
        customers={"CUST-A": "SP-A", "CUST-B": "SP-B"},
        charges={"DHD-CHARGE": "DHD", "DDP": "DDP"},
        offered={"DHD-CHARGE", "DDP"},  # what a partner is offered
        countries={"United Kingdom"},
        addresses=[],  # existing {name, customer, address_line1, pincode}
        inserted=[],
    )


class FakeDoc:
    def __init__(self, data):
        self.data = data
        self.name = None
        self.flags = types.SimpleNamespace()

    def insert(self, ignore_permissions=False):
        assert ignore_permissions
        self.name = f"ADDR-{len(STATE['inserted']) + 1}-Shipping"
        STATE["inserted"].append(self.data)
        STATE["addresses"].append(
            {
                "name": self.name,
                "customer": self.data["links"][0]["link_name"],
                "address_line1": self.data["address_line1"],
                "pincode": self.data["pincode"],
            }
        )
        return self


def _load():
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = FakeValidationError
    frappe.PermissionError = FakePermissionError
    frappe.DoesNotExistError = FakeDoesNotExistError
    frappe._ = lambda text: text
    frappe.bold = lambda text: text

    def throw(msg, exc=Exception):
        raise exc(msg)

    frappe.throw = throw
    frappe.whitelist = lambda **kw: (lambda fn: fn)

    import json

    frappe.parse_json = json.loads

    def exists(doctype, name):
        if doctype == "Customer":
            return name in STATE["customers"]
        if doctype == "Country":
            return name in STATE["countries"]
        return False

    def get_value(doctype, name, field):
        assert doctype == "Delivery Charges"
        return 0

    def sql(query, params, as_dict=False):
        customer = params[0]
        return [_dict(a) for a in STATE["addresses"] if a["customer"] == customer]

    frappe.db = types.SimpleNamespace(exists=exists, get_value=get_value, sql=sql)
    frappe.get_doc = FakeDoc

    utils = types.ModuleType("frappe.utils")
    utils.cstr = lambda v: "" if v is None else str(v)
    frappe.utils = utils

    charge_pricing = types.ModuleType(f"{PKG}.charge_pricing")
    charge_pricing.DHD_ORDER_TYPE = "DHD"

    def get_charge(name):
        if name not in STATE["charges"]:
            return None
        return _dict(name=name, order_type=STATE["charges"][name])

    def validated_partner_charge(name, customer):
        if name not in STATE["offered"]:
            raise FakePermissionError("not available")
        return get_charge(name)

    charge_pricing.get_charge = get_charge
    charge_pricing.validated_partner_charge = validated_partner_charge
    charge_pricing.assert_available = lambda name: None

    gate = types.ModuleType(f"{PKG}.partner_gate")
    gate.customer_scope_partners = lambda user=None: STATE["partners"]
    gate.is_customer_in_scope = lambda customer, partners: (
        STATE["customers"].get(customer) in partners if partners else False
    )

    email = types.ModuleType(f"{PKG}.email_validation")

    def validate_optional_email(value):
        if "@" not in value:
            raise FakeValidationError("bad email")
        return value

    email.validate_optional_email = validate_optional_email

    pkg = types.ModuleType(PKG)
    pkg.__path__ = [str(API_DIR)]
    fakes = {
        "frappe": frappe,
        "frappe.utils": utils,
        "posawesome": types.ModuleType("posawesome"),
        "posawesome.posawesome": types.ModuleType("posawesome.posawesome"),
        PKG: pkg,
        f"{PKG}.charge_pricing": charge_pricing,
        f"{PKG}.partner_gate": gate,
        f"{PKG}.email_validation": email,
    }
    with mock.patch.dict(sys.modules, fakes):
        spec = importlib.util.spec_from_file_location(f"{PKG}.order_address", API_DIR / "order_address.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module, fakes


MODULE, FAKES = _load()
GOOD = {
    "address_line1": " 10  High Street ",
    "city": "Peterborough",
    "postcode": "pe1 1aa",
    "country": "United Kingdom",
}


def create(customer="CUST-A", charge="DHD-CHARGE", address=None):
    return MODULE.create_order_address(customer, charge, GOOD if address is None else address)


class TestCreateOrderAddress(unittest.TestCase):
    def setUp(self):
        _reset()
        # create_order_address imports its siblings at call time, so the fakes stay in place.
        patcher = mock.patch.dict(sys.modules, FAKES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_create_path(self):
        result = create(address={**GOOD, "email": "a@b.co", "phone": "01733 000000", "county": "Cambs"})
        self.assertEqual(result, {"name": "ADDR-1-Shipping", "created": True})
        data = STATE["inserted"][0]
        self.assertEqual(data["address_type"], "Shipping")
        self.assertEqual(data["links"], [{"link_doctype": "Customer", "link_name": "CUST-A"}])
        self.assertEqual(data["address_line1"], "10 High Street")  # stripped and collapsed
        self.assertEqual(data["pincode"], "pe1 1aa")
        self.assertEqual(data["email_id"], "a@b.co")
        self.assertEqual(data["county"], "Cambs")

    def test_dedupe_returns_existing(self):
        first = create()
        again = create(address={**GOOD, "address_line1": "10 high street.", "postcode": "PE1  1AA"})
        self.assertEqual(again, {"name": first["name"], "created": False})
        self.assertEqual(len(STATE["inserted"]), 1)

    def test_same_line_other_postcode_is_a_new_address(self):
        create()
        self.assertTrue(create(address={**GOOD, "postcode": "PE2 2BB"})["created"])

    def test_dedupe_is_per_customer(self):
        STATE["partners"] = None
        create("CUST-A")
        self.assertTrue(create("CUST-B")["created"])

    def test_non_dhd_charge_rejected(self):
        with self.assertRaises(FakeValidationError):
            create(charge="DDP")
        self.assertEqual(STATE["inserted"], [])

    def test_missing_charge_rejected(self):
        for charge in (None, "", ["DHD-CHARGE"]):
            with self.subTest(charge=charge), self.assertRaises(FakeValidationError):
                create(charge=charge)

    def test_partner_charge_not_offered_rejected(self):
        STATE["offered"].discard("DHD-CHARGE")
        with self.assertRaises(FakePermissionError):
            create()

    def test_staff_unknown_charge_rejected(self):
        STATE["partners"] = None
        with self.assertRaises(FakePermissionError):
            create(charge="NOPE")

    def test_staff_can_create_for_any_customer(self):
        STATE["partners"] = None
        self.assertTrue(create("CUST-B")["created"])

    def test_partner_out_of_scope_customer_rejected(self):
        with self.assertRaises(FakePermissionError):
            create("CUST-B")
        self.assertEqual(STATE["inserted"], [])

    def test_partner_with_no_partner_rejected(self):
        STATE["partners"] = ["__none__"]
        with self.assertRaises(FakePermissionError):
            create()

    def test_unknown_field_rejected(self):
        for key in ("address_title", "links", "disabled", "name", "doctype", "address_type"):
            with self.subTest(key=key), self.assertRaises(FakeValidationError):
                create(address={**GOOD, key: "x"})
        self.assertEqual(STATE["inserted"], [])

    def test_missing_required_field_rejected(self):
        for key in ("address_line1", "city", "postcode", "country"):
            bad = {k: v for k, v in GOOD.items() if k != key}
            with self.subTest(key=key), self.assertRaises(FakeValidationError):
                create(address=bad)
            with self.subTest(key=key, blank=True), self.assertRaises(FakeValidationError):
                create(address={**GOOD, key: "   "})

    def test_bad_values_rejected(self):
        for address in (
            {**GOOD, "city": "x" * 141},
            {**GOOD, "email": "not-an-email"},
            {**GOOD, "country": "Atlantis"},
            {**GOOD, "phone": ["1"]},
            {**GOOD, "pincode": "PE1 1AA", "postcode": "PE2 2BB"},
            "[1, 2]",
            "not json",
            None,
        ):
            with self.subTest(address=address), self.assertRaises(FakeValidationError):
                create(address=address) if address is not None else MODULE.create_order_address(
                    "CUST-A", "DHD-CHARGE", None
                )

    def test_json_string_address_is_accepted(self):
        import json

        self.assertTrue(create(address=json.dumps(GOOD))["created"])

    def test_unknown_customer_rejected_for_staff(self):
        STATE["partners"] = None
        with self.assertRaises(FakeDoesNotExistError):
            create("CUST-Z")


if __name__ == "__main__":
    unittest.main()
