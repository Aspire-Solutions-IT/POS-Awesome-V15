import importlib.util
import json
import pathlib
import sys
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
API_DIR = REPO_ROOT / "posawesome" / "posawesome" / "api"
PACKAGE = "posawesome_shifts_under_test"


class _AttrDict(dict):
	"""Minimal stand-in for frappe._dict: supports both dict and attribute access."""

	def __getattr__(self, name):
		try:
			return self[name]
		except KeyError as exc:
			raise AttributeError(name) from exc


class _FakeDoc:
	def __init__(self, **fields):
		self.__dict__.update(fields)
		self.inserted = False
		self.balance_details = []

	def get(self, key, default=None):
		return self.__dict__.get(key, default)

	def set(self, key, value):
		setattr(self, key, value)

	def insert(self, ignore_permissions=False):
		self.inserted = True
		self.name = self.__dict__.get("name") or "NEW-SHIFT"
		return self

	def as_dict(self):
		return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

	def get_password(self, fieldname):
		return self.__dict__.get(fieldname)


def _install_frappe_stub():
	frappe_module = types.ModuleType("frappe")
	frappe_module._ = lambda text: text

	def _throw(message, *args, **kwargs):
		raise Exception(message)

	frappe_module.throw = _throw
	frappe_module.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe_module.session = types.SimpleNamespace(user="cashier@example.com")
	frappe_module._dict = _AttrDict
	frappe_module.local = types.SimpleNamespace(lang=None)
	frappe_module.get_all = lambda *args, **kwargs: []
	frappe_module.get_list = lambda *args, **kwargs: []
	frappe_module.get_doc = lambda *args, **kwargs: None
	frappe_module.get_cached_value = lambda *args, **kwargs: "GBP"
	frappe_module.db = types.SimpleNamespace(
		sql=lambda *args, **kwargs: [],
		get_all=lambda *args, **kwargs: [],
		get_single_value=lambda *args, **kwargs: 0,
	)

	utils_module = types.ModuleType("frappe.utils")
	utils_module.cint = lambda value: int(value or 0)
	utils_module.nowdate = lambda: "2026-08-28"
	utils_module.get_datetime = lambda *args, **kwargs: "2026-08-28 09:00:00"
	utils_module.getdate = lambda *args, **kwargs: "2026-08-28"
	frappe_module.utils = utils_module

	sys.modules["frappe"] = frappe_module
	sys.modules["frappe.utils"] = utils_module
	return frappe_module


def _load_module(module_name, file_name):
	spec = importlib.util.spec_from_file_location(
		f"{PACKAGE}.{module_name}", API_DIR / file_name
	)
	module = importlib.util.module_from_spec(spec)
	sys.modules[f"{PACKAGE}.{module_name}"] = module
	spec.loader.exec_module(module)
	return module


def _load_shifts_module():
	"""Load shifts.py as part of a stub package so its relative imports resolve."""
	package = types.ModuleType(PACKAGE)
	package.__path__ = [str(API_DIR)]
	sys.modules[PACKAGE] = package

	# shifts.py only needs get_version out of utilities, which drags in psutil and the
	# rest of the app otherwise.
	utilities_stub = types.ModuleType(f"{PACKAGE}.utilities")
	utilities_stub.get_version = lambda: 15
	sys.modules[f"{PACKAGE}.utilities"] = utilities_stub

	# employees is loaded for real so the supervisor gate is genuinely exercised.
	_load_module("employees", "employees.py")
	return _load_module("shifts", "shifts.py")


PROFILES = [
	_AttrDict({"name": "POS-A", "company": "Test Co", "currency": "GBP"}),
	_AttrDict({"name": "POS-B", "company": "Test Co", "currency": "GBP"}),
]


class ShiftsApiTestCase(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.frappe = _install_frappe_stub()
		cls.shifts = _load_shifts_module()

	def setUp(self):
		frappe = self.shifts.frappe
		frappe.session.user = "cashier@example.com"
		frappe.db.sql = lambda *args, **kwargs: list(PROFILES)
		frappe.db.get_all = lambda *args, **kwargs: []
		frappe.db.get_single_value = lambda *args, **kwargs: 0
		frappe.get_list = lambda *args, **kwargs: []
		frappe.get_cached_value = lambda *args, **kwargs: "GBP"
		frappe.get_all = lambda *args, **kwargs: [{"user": "supervisor@example.com"}]
		frappe.get_doc = self._get_doc
		self.created_shifts = []

	def _get_doc(self, doctype, name=None, *args, **kwargs):
		if isinstance(doctype, dict):
			doc = _FakeDoc(**doctype)
			self.created_shifts.append(doc)
			return doc
		if doctype == "POS Profile":
			return _FakeDoc(name=name, company="Test Co", currency="GBP")
		if doctype == "Company":
			return _FakeDoc(name=name)
		if doctype == "POS Opening Shift":
			return _FakeDoc(name=name, pos_profile="POS-B", user="cashier@example.com")
		if doctype == "User":
			return _FakeDoc(
				name=name,
				enabled=1,
				full_name="Supervisor",
				posa_pos_pin="1234",
				posa_is_pos_supervisor=1,
			)
		raise AssertionError(f"unexpected get_doc for {doctype}")

	def _switch(self, **overrides):
		args = {
			"target_profile": "POS-B",
			"current_profile": "POS-A",
			"balance_details": json.dumps([]),
			"supervisor_user": "supervisor@example.com",
			"pin": "1234",
		}
		args.update(overrides)
		return self.shifts.switch_pos_profile(**args)


class TestSwitchPosProfile(ShiftsApiTestCase):
	def test_rejects_profile_the_user_is_not_assigned_to(self):
		with self.assertRaises(Exception) as ctx:
			self._switch(target_profile="POS-UNASSIGNED")
		self.assertIn("not assigned", str(ctx.exception))

	def test_rejects_switching_to_the_current_profile(self):
		with self.assertRaises(Exception) as ctx:
			self._switch(target_profile="POS-A")
		self.assertIn("already on this POS profile", str(ctx.exception))

	def test_rejects_a_supervisor_who_is_not_on_the_current_terminal(self):
		self.shifts.frappe.get_all = lambda *args, **kwargs: [{"user": "cashier@example.com"}]
		with self.assertRaises(Exception) as ctx:
			self._switch()
		self.assertIn("not assigned to this POS profile", str(ctx.exception))

	def test_rejects_a_wrong_pin(self):
		with self.assertRaises(Exception) as ctx:
			self._switch(pin="0000")
		self.assertIn("Invalid supervisor PIN", str(ctx.exception))

	def test_rejects_a_non_supervisor_even_with_a_valid_pin(self):
		original = self._get_doc

		def get_doc(doctype, name=None, *args, **kwargs):
			if doctype == "User":
				return _FakeDoc(
					name=name,
					enabled=1,
					full_name="Cashier",
					posa_pos_pin="1234",
					posa_is_pos_supervisor=0,
				)
			return original(doctype, name, *args, **kwargs)

		self.shifts.frappe.get_doc = get_doc
		with self.assertRaises(Exception) as ctx:
			self._switch()
		self.assertIn("Only POS supervisors", str(ctx.exception))

	def test_requires_supervisor_and_pin(self):
		with self.assertRaises(Exception) as ctx:
			self._switch(pin=None)
		self.assertIn("Supervisor and PIN are required", str(ctx.exception))

	def test_resumes_an_existing_open_shift_instead_of_creating_a_duplicate(self):
		self.shifts.frappe.db.get_all = lambda *args, **kwargs: [
			{"name": "SHIFT-B", "pos_profile": "POS-B"}
		]

		data = self._switch()

		self.assertEqual(data["pos_opening_shift"]["name"], "SHIFT-B")
		self.assertEqual(self.created_shifts, [])

	def test_creates_a_shift_using_the_profiles_own_company(self):
		data = self._switch()

		self.assertEqual(len(self.created_shifts), 1)
		created = self.created_shifts[0]
		self.assertTrue(created.inserted)
		self.assertEqual(created.pos_profile, "POS-B")
		self.assertEqual(created.company, "Test Co")
		self.assertEqual(created.user, "cashier@example.com")
		self.assertEqual(created.docstatus, 1)
		self.assertEqual(data["pos_profile"].name, "POS-B")


class TestCheckOpeningShift(ShiftsApiTestCase):
	def setUp(self):
		super().setUp()
		self.shifts.frappe.db.get_all = lambda *args, **kwargs: [
			{"name": "SHIFT-B", "pos_profile": "POS-B"},
			{"name": "SHIFT-A", "pos_profile": "POS-A"},
		]

	def test_returns_the_newest_open_shift_by_default(self):
		data = self.shifts.check_opening_shift("cashier@example.com")
		self.assertEqual(data["pos_opening_shift"].name, "SHIFT-B")

	def test_prefers_the_shift_the_terminal_was_operating(self):
		data = self.shifts.check_opening_shift("cashier@example.com", preferred_shift="SHIFT-A")
		self.assertEqual(data["pos_opening_shift"].name, "SHIFT-A")
		self.assertEqual(data["pos_profile"].name, "POS-A")

	def test_falls_back_to_newest_when_the_preferred_shift_is_gone(self):
		data = self.shifts.check_opening_shift("cashier@example.com", preferred_shift="SHIFT-CLOSED")
		self.assertEqual(data["pos_opening_shift"].name, "SHIFT-B")

	def test_returns_empty_when_no_shift_is_open(self):
		self.shifts.frappe.db.get_all = lambda *args, **kwargs: []
		self.assertEqual(self.shifts.check_opening_shift("cashier@example.com"), "")


class TestGetSwitchablePosProfiles(ShiftsApiTestCase):
	def test_flags_open_shifts_and_only_asks_balances_for_the_rest(self):
		self.shifts.frappe.db.get_all = lambda *args, **kwargs: [
			{"name": "SHIFT-A", "pos_profile": "POS-A"}
		]
		requested_profiles = {}

		def get_list(doctype, filters=None, **kwargs):
			requested_profiles["value"] = filters["parent"][1]
			return [{"mode_of_payment": "Cash", "parent": "POS-B"}]

		self.shifts.frappe.get_list = get_list

		data = self.shifts.get_switchable_pos_profiles()

		by_name = {profile["name"]: profile for profile in data["pos_profiles_data"]}
		self.assertEqual(by_name["POS-A"]["open_shift"], "SHIFT-A")
		self.assertIsNone(by_name["POS-B"]["open_shift"])
		self.assertEqual(requested_profiles["value"], ["POS-B"])
		self.assertEqual(data["payments_method"][0]["currency"], "GBP")


if __name__ == "__main__":
	unittest.main()
