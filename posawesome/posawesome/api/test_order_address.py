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


class FakeDuplicateEntryError(Exception):
    pass


class FakeDeadlockError(Exception):
    pass


class _dict(dict):
    __getattr__ = dict.get


# Reset per test.
STATE = {}


def _reset():
    STATE.clear()
    STATE.update(
        partners=["SP-A"],  # None = staff
        user="staff@example.com",
        user_types={"staff@example.com": "System User", "web@example.com": "Website User"},
        can_create_address=True,
        can_read_customer=True,
        profile="PROFILE-1",  # resolved POS Profile of the caller
        restricted={"DHD-CHARGE"},  # charges with Delivery Charges POS Profile rows
        lookups=[],
        disabled_charges=set(),
        duplicate_once=False,
        customers={"CUST-A": "SP-A", "CUST-B": "SP-B"},
        # Delivery Charges.order_type is an Order Type document id, NOT the name "DHD".
        charges={"DHD-CHARGE": "OT-0001", "DDP": "OT-0002"},
        order_type_names={"OT-0001": "DHD", "OT-0002": "DDP"},
        unreadable_addresses=set(),
        reassign_on_lock=None,  # (customer, partner) applied when the customer row is locked
        deadlocks=0,
        savepoints=[],
        rollbacks=[],
        events=[],
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
        STATE["insert_ignore"] = ignore_permissions
        if STATE["deadlocks"]:
            STATE["deadlocks"] -= 1
            raise FakeDeadlockError("deadlock")
        if STATE["duplicate_once"]:
            STATE["duplicate_once"] = False
            # the concurrent request's address is now there
            STATE["addresses"].append(
                {
                    "name": "ADDR-RACE-Shipping",
                    "customer": self.data["links"][0]["link_name"],
                    "address_line1": self.data["address_line1"],
                    "pincode": self.data["pincode"],
                    "address_type": "Shipping",
                    "disabled": 0,
                }
            )
            raise FakeDuplicateEntryError("dup")
        self.name = f"{self.data['address_title']}-Shipping"
        STATE["inserted"].append(self.data)
        STATE["addresses"].append(
            {
                "name": self.name,
                "customer": self.data["links"][0]["link_name"],
                "address_line1": self.data["address_line1"],
                "pincode": self.data["pincode"],
                "address_type": "Shipping",
                "disabled": 0,
            }
        )
        return self


def _load():
    frappe = types.ModuleType("frappe")
    frappe.ValidationError = FakeValidationError
    frappe.PermissionError = FakePermissionError
    frappe.DoesNotExistError = FakeDoesNotExistError
    frappe.DuplicateEntryError = FakeDuplicateEntryError
    frappe.QueryDeadlockError = FakeDeadlockError
    frappe.generate_hash = lambda length=10: "h" * length

    class Session:
        user = property(lambda self: STATE["user"])

    frappe.session = Session()
    def has_permission(doctype, ptype="read", doc=None):
        if doctype == "Address":
            if ptype == "read" and doc is not None:
                return doc not in STATE["unreadable_addresses"]
            return STATE["can_create_address"]
        return STATE["can_read_customer"]

    frappe.has_permission = has_permission
    frappe._ = lambda text: text
    frappe.bold = lambda text: text

    def throw(msg, exc=Exception):
        raise exc(msg)

    frappe.throw = throw
    frappe.whitelist = lambda **kw: (lambda fn: fn)

    import json

    frappe.parse_json = json.loads

    def exists(doctype, name):
        if doctype == "Delivery Charges POS Profile":
            return name["parent"] in STATE["restricted"]
        if doctype == "Customer":
            return name in STATE["customers"]
        if doctype == "Country":
            return name in STATE["countries"]
        return False

    def get_value(doctype, name, field, for_update=False, as_dict=False):
        if doctype == "User":
            return STATE["user_types"].get(name)
        if doctype == "Order Type":
            assert field == "order_type_name"
            return STATE["order_type_names"].get(name)
        if doctype == "Customer":
            if for_update:
                STATE["events"].append("lock")
                if STATE["reassign_on_lock"]:
                    cust, partner = STATE["reassign_on_lock"]
                    STATE["customers"][cust] = partner
            if name not in STATE["customers"]:
                return None
            if as_dict:
                return _dict(name=name, default_sales_partner=STATE["customers"][name])
            return name
        assert doctype == "Delivery Charges"
        return 1 if name in STATE["disabled_charges"] else 0

    def sql(query, params, as_dict=False):
        STATE["lookups"].append(params[0])
        STATE["events"].append("sql")
        assert "FOR UPDATE" not in query and "SHARE" not in query and "'Shipping'" in query and "parenttype = 'Address'" in query
        customer = params[0]
        return [
            _dict(a)
            for a in STATE["addresses"]
            if a["customer"] == customer and a.get("address_type", "Shipping") == "Shipping" and not a.get("disabled")
        ]

    def rollback(save_point=None):
        STATE["rollbacks"].append(save_point)

    frappe.db = types.SimpleNamespace(
        exists=exists,
        get_value=get_value,
        sql=sql,
        savepoint=lambda name: STATE["savepoints"].append(name),
        rollback=rollback,
    )
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
    charge_pricing.server_profile_context = lambda user=None: (STATE["profile"], "Co")

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
        self.assertEqual(result, {"name": "CUST-A-hhhhhhhhhh-Shipping", "created": True})
        data = STATE["inserted"][0]
        self.assertTrue(STATE["insert_ignore"])  # scoped partner
        self.assertEqual(data["address_type"], "Shipping")
        self.assertEqual(data["links"], [{"link_doctype": "Customer", "link_name": "CUST-A"}])
        self.assertEqual(data["address_line1"], "10 High Street")  # stripped and collapsed
        self.assertEqual(data["pincode"], "pe1 1aa")
        self.assertNotIn("High", data["address_title"])  # opaque: street text never drives the name
        self.assertLessEqual(len(data["address_title"]) + len("-Shipping"), 140)
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

    # --- staff authorisation -------------------------------------------------------------
    def test_staff_uses_normal_permissions(self):
        STATE["partners"] = None
        self.assertTrue(create("CUST-B")["created"])
        self.assertFalse(STATE["insert_ignore"])

    def test_unrelated_user_denied_before_any_lookup(self):
        STATE["partners"] = None
        for user in ("web@example.com", "Guest", "nobody@example.com"):
            STATE["user"] = user
            with self.subTest(user=user), self.assertRaises(FakePermissionError):
                create()
        self.assertEqual(STATE["lookups"], [])
        self.assertEqual(STATE["inserted"], [])

    def test_staff_without_address_create_or_customer_read_denied(self):
        STATE["partners"] = None
        for key in ("can_create_address", "can_read_customer"):
            STATE[key] = False
            with self.subTest(key=key), self.assertRaises(FakePermissionError):
                create()
            STATE[key] = True
        self.assertEqual(STATE["lookups"], [])

    def test_out_of_scope_partner_denied_before_any_lookup(self):
        with self.assertRaises(FakePermissionError):
            create("CUST-B")
        self.assertEqual(STATE["lookups"], [])

    # --- charge / profile -----------------------------------------------------------------
    def test_profile_restricted_charge_without_profile_denied_for_partner(self):
        STATE["profile"] = None
        with self.assertRaises(FakePermissionError):
            create()
        self.assertEqual(STATE["inserted"], [])
        STATE["profile"] = "PROFILE-1"
        self.assertTrue(create()["created"])

    def test_unrestricted_charge_without_profile_ok_for_partner(self):
        STATE["profile"] = None
        STATE["restricted"].clear()
        self.assertTrue(create()["created"])

    def test_disabled_charge_denied_for_staff(self):
        STATE["partners"] = None
        STATE["disabled_charges"].add("DHD-CHARGE")
        with self.assertRaises(FakePermissionError):
            create()

    # --- dedupe ---------------------------------------------------------------------------
    def test_billing_and_disabled_addresses_are_not_reused(self):
        STATE["addresses"] += [
            {"name": "B", "customer": "CUST-A", "address_line1": "10 High Street", "pincode": "PE1 1AA",
             "address_type": "Billing", "disabled": 0},
            {"name": "D", "customer": "CUST-A", "address_line1": "10 High Street", "pincode": "PE1 1AA",
             "address_type": "Shipping", "disabled": 1},
        ]
        result = create()
        self.assertTrue(result["created"])
        self.assertNotIn(result["name"], ("B", "D"))

    def test_duplicate_entry_returns_the_concurrent_address(self):
        STATE["duplicate_once"] = True
        self.assertEqual(create(), {"name": "ADDR-RACE-Shipping", "created": False})

    def test_charge_order_type_is_resolved_by_name_not_compared_as_id(self):
        # DHD-CHARGE stores the opaque id OT-0001; only its order_type_name is "DHD".
        self.assertNotEqual(STATE["charges"]["DHD-CHARGE"], "DHD")
        self.assertTrue(create()["created"])
        STATE["order_type_names"]["OT-0001"] = "Other"
        with self.assertRaises(FakeValidationError):
            create()
        # An id that merely equals the string "DHD" is not enough either.
        STATE["charges"]["DHD-CHARGE"] = "DHD"
        with self.assertRaises(FakeValidationError):
            create()

    def test_staff_match_without_address_read_is_not_reused_or_revealed(self):
        STATE["partners"] = None
        STATE["addresses"].append(
            {"name": "SECRET-Shipping", "customer": "CUST-A", "address_line1": "10 High Street",
             "pincode": "PE1 1AA", "address_type": "Shipping", "disabled": 0}
        )
        STATE["unreadable_addresses"].add("SECRET-Shipping")
        result = create()
        self.assertTrue(result["created"])
        self.assertNotEqual(result["name"], "SECRET-Shipping")
        STATE["unreadable_addresses"].clear()
        self.assertEqual(create(), {"name": "SECRET-Shipping", "created": False})

    def test_partner_reassigned_while_waiting_for_lock_is_denied(self):
        STATE["reassign_on_lock"] = ("CUST-A", "SP-B")  # pre-check passes, locked row differs
        with self.assertRaises(FakePermissionError):
            create()
        self.assertEqual(STATE["inserted"], [])
        self.assertEqual(STATE["lookups"], [])

    def test_customer_gone_at_lock_is_denied(self):
        original = FAKES["frappe"].db.get_value

        def vanish(doctype, name, field, for_update=False, as_dict=False):
            if doctype == "Customer" and for_update:
                return None
            return original(doctype, name, field, for_update, as_dict)

        with mock.patch.object(FAKES["frappe"].db, "get_value", vanish):
            with self.assertRaises(FakePermissionError):
                create()

    def test_lock_is_taken_before_the_dedupe_read(self):
        create()
        self.assertEqual(STATE["events"][:2], ["lock", "sql"])

    def test_deadlock_is_retried_once(self):
        STATE["deadlocks"] = 1
        self.assertTrue(create()["created"])
        self.assertEqual(STATE["events"].count("lock"), 2)
        self.assertIn(None, STATE["rollbacks"])  # whole-transaction rollback before the retry
        STATE["addresses"].clear()
        STATE["deadlocks"] = 2
        with self.assertRaises(FakeDeadlockError):
            create()

    def test_duplicate_rolls_back_to_savepoint_only(self):
        STATE["duplicate_once"] = True
        create()
        self.assertEqual(STATE["savepoints"], ["order_address_insert"])
        self.assertEqual(STATE["rollbacks"], ["order_address_insert"])

    def test_duplicate_without_a_match_is_reraised(self):
        STATE["duplicate_once"] = True
        original = MODULE._existing_address
        calls = []

        def none_after_insert(*a, **k):
            calls.append(1)
            return None

        with mock.patch.object(MODULE, "_existing_address", none_after_insert):
            with self.assertRaises(FakeDuplicateEntryError):
                create()
        self.assertEqual(STATE["rollbacks"], ["order_address_insert"])

    # --- plain text only ------------------------------------------------------------------
    def test_markup_and_json_rejected_in_every_field(self):
        payloads = (
            '<img src=x onerror=alert(1)>',
            "<script>alert(1)</script>",
            "10 High St >",
            "&lt;b&gt;",
            "&#60;b",
            '{"a": 1}',
            "[1, 2]",
        )
        for field in ("address_line1", "address_line2", "city", "county", "postcode", "phone"):
            for payload in payloads:
                with self.subTest(field=field, payload=payload), self.assertRaises(FakeValidationError):
                    create(address={**GOOD, field: payload})
        with self.assertRaises(FakeValidationError):
            create(address={**GOOD, "country": "<b>United Kingdom</b>"})
        self.assertEqual(STATE["inserted"], [])

    def test_plain_punctuation_is_kept_and_control_chars_stripped(self):
        result = create(address={**GOOD, "address_line1": "Flat 2\x00\x07, O'Brien & Sons (rear) {yard}"})
        self.assertTrue(result["created"])
        self.assertEqual(STATE["inserted"][0]["address_line1"], "Flat 2, O'Brien & Sons (rear) {yard}")

    def test_title_is_opaque_even_for_hostile_street_text(self):
        create(address={**GOOD, "address_line1": "Evil Street"})
        self.assertNotIn("Evil", STATE["inserted"][0]["address_title"])


if __name__ == "__main__":
    unittest.main()
