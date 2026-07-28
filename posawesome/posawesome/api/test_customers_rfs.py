import importlib.util
import json
import pathlib
import sys
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class _FakeCustomerDoc:
	def __init__(self, payload):
		self.payload = dict(payload)
		self.customer_name = payload.get("customer_name")
		self.customer_group = None
		self.territory = None
		self.name = payload.get("customer_name")

	def save(self):
		return self


class _FakeAddressDoc:
	def __init__(self, name):
		self.name = name
		self.links = []
		self.saved = False

	def append(self, fieldname, value):
		if fieldname == "links":
			self.links.append(value)

	def save(self):
		self.saved = True
		return self


class TestPosCustomersRfs(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls._install_stubs()
		cls.module = cls._load_module()

	@classmethod
	def _install_stubs(cls):
		posawesome_pkg = types.ModuleType("posawesome")
		posawesome_pkg.__path__ = []
		posawesome_inner_pkg = types.ModuleType("posawesome.posawesome")
		posawesome_inner_pkg.__path__ = []
		posawesome_api_pkg = types.ModuleType("posawesome.posawesome.api")
		posawesome_api_pkg.__path__ = []

		frappe_module = types.ModuleType("frappe")
		frappe_module._ = lambda text: text
		frappe_module.throw = lambda message: (_ for _ in ()).throw(Exception(message))
		frappe_module.whitelist = lambda *args, **kwargs: (lambda fn: fn)
		frappe_module.log_error = lambda *args, **kwargs: None

		class _FakeDb:
			def __init__(self):
				self.count_calls = []
				self.exists_calls = []
				self.get_value_calls = []
				self.exists_return_value = False
				self.address_flags = {}

			def count(self, doctype, filters):
				self.count_calls.append((doctype, filters))
				return 7

			def exists(self, doctype, filters):
				self.exists_calls.append((doctype, filters))
				return self.exists_return_value

			def get_value(self, doctype, name, fieldname):
				self.get_value_calls.append((doctype, name, fieldname))
				if doctype == "Address" and fieldname == "posa_is_store_collection_point":
					return self.address_flags.get(name, 0)
				return None

		frappe_module.db = _FakeDb()
		frappe_module.last_get_all = None
		frappe_module.last_customer_doc = None
		frappe_module.last_address_doc = None
		frappe_module.address_docs = {}

		def fake_get_all(
			doctype,
			filters=None,
			fields=None,
			order_by=None,
			limit_start=None,
			limit_page_length=None,
			pluck=None,
		):
			frappe_module.last_get_all = {
				"doctype": doctype,
				"filters": filters,
				"fields": fields,
				"order_by": order_by,
				"limit_start": limit_start,
				"limit_page_length": limit_page_length,
				"pluck": pluck,
			}
			if doctype == "Customer" and pluck == "name":
				if filters and filters.get("name") == ["in", ["13682"]]:
					return ["13682"]
				return []
			if doctype == "Address":
				return [
					{
						"name": "STORE-ADDR-1",
						"address_title": "Main Store",
						"address_line1": "1 High Street",
						"city": "London",
						"posa_is_store_collection_point": 1,
					}
				]
			return []

		def fake_get_doc(*args, **kwargs):
			if len(args) == 2 and args[0] == "Address":
				name = args[1]
				doc = frappe_module.address_docs.get(name) or _FakeAddressDoc(name)
				frappe_module.address_docs[name] = doc
				frappe_module.last_address_doc = doc
				return doc

			payload = args[0]
			doc = _FakeCustomerDoc(payload)
			frappe_module.last_customer_doc = doc
			return doc

		frappe_module.get_all = fake_get_all
		frappe_module.get_doc = fake_get_doc

		utils_module = types.ModuleType("frappe.utils")
		utils_module.nowdate = lambda: "2026-06-12"
		utils_module.flt = lambda value, *args, **kwargs: float(value or 0)
		utils_module.cstr = lambda value: "" if value is None else str(value)
		utils_module.get_datetime = lambda value: type("Dt", (), {"isoformat": lambda self: value})()

		caching_module = types.ModuleType("frappe.utils.caching")
		caching_module.redis_cache = lambda ttl=None: (lambda fn: fn)

		loyalty_module = types.ModuleType(
			"erpnext.accounts.doctype.loyalty_program.loyalty_program"
		)
		loyalty_module.get_loyalty_program_details_with_points = (
			lambda *args, **kwargs: {}
		)

		api_utils_module = types.ModuleType("posawesome.posawesome.api.utils")
		api_utils_module.fetch_sales_person_names = lambda *args, **kwargs: []

		stored_value_module = types.ModuleType("posawesome.posawesome.api.stored_value")
		stored_value_module.get_stored_value_summary = lambda *args, **kwargs: {}

		sys.modules["posawesome"] = posawesome_pkg
		sys.modules["posawesome.posawesome"] = posawesome_inner_pkg
		sys.modules["posawesome.posawesome.api"] = posawesome_api_pkg
		sys.modules["frappe"] = frappe_module
		sys.modules["frappe.utils"] = utils_module
		sys.modules["frappe.utils.caching"] = caching_module
		sys.modules[
			"erpnext.accounts.doctype.loyalty_program.loyalty_program"
		] = loyalty_module
		sys.modules["posawesome.posawesome.api.utils"] = api_utils_module
		sys.modules["posawesome.posawesome.api.stored_value"] = stored_value_module

		cls.frappe = frappe_module

	@classmethod
	def _load_module(cls):
		module_name = "posawesome.posawesome.api.customers"
		file_path = (
			REPO_ROOT
			/ "posawesome"
			/ "posawesome"
			/ "api"
			/ "customers.py"
		)
		spec = importlib.util.spec_from_file_location(module_name, file_path)
		module = importlib.util.module_from_spec(spec)
		sys.modules[module_name] = module
		spec.loader.exec_module(module)
		return module

	def setUp(self):
		self.frappe.last_get_all = None
		self.frappe.last_customer_doc = None
		self.frappe.last_address_doc = None
		self.frappe.address_docs = {}
		self.frappe.db.exists_return_value = False
		self.frappe.db.address_flags = {}

	def test_get_customer_names_filters_to_rfs_customers(self):
		self.module.get_customer_names('{"customer_groups":[]}', limit=25)

		self.assertEqual(self.frappe.last_get_all["doctype"], "Customer")
		self.assertEqual(
			self.frappe.last_get_all["filters"],
			{"disabled": 0, "rfs_customer": 1},
		)

	def test_get_customer_names_excludes_customer_13682(self):
		original_get_all = self.frappe.get_all

		def fake_customers(*args, **kwargs):
			if args and args[0] == "Customer" and not kwargs.get("pluck"):
				return [
					{"name": "13682", "customer_name": "Hidden Customer"},
					{"name": "CUST-1001", "customer_name": "Visible Customer"},
				]
			return original_get_all(*args, **kwargs)

		self.frappe.get_all = fake_customers
		try:
			rows = self.module.get_customer_names('{"customer_groups":[]}', limit=25)
		finally:
			self.frappe.get_all = original_get_all

		self.assertEqual([row["name"] for row in rows], ["CUST-1001"])

	def test_get_customers_count_filters_to_rfs_customers(self):
		count = self.module.get_customers_count('{"customer_groups":[]}')

		self.assertEqual(count, 6)
		self.assertEqual(
			self.frappe.db.count_calls[-1],
			("Customer", {"disabled": 0, "rfs_customer": 1}),
		)

	def test_create_customer_marks_customer_as_rfs(self):
		customer = self.module.create_customer(
			customer_name="RFS POS Customer",
			company="Agile",
			pos_profile_doc='{"posa_allow_duplicate_customer_names": 1}',
			customer_group="Retail",
			territory="United Kingdom",
			method="create",
		)

		self.assertEqual(customer.payload["rfs_customer"], 1)
		self.assertEqual(self.frappe.last_customer_doc.payload["rfs_customer"], 1)
		self.assertEqual(customer.payload["auto_allocate_sales_orders"], 1)
		self.assertEqual(self.frappe.last_customer_doc.payload["auto_allocate_sales_orders"], 1)

	def test_create_customer_passes_phone_and_email_to_created_address(self):
		captured = {}
		original_make_address = self.module.make_address

		def fake_make_address(args):
			captured["args"] = json.loads(args) if isinstance(args, str) else args
			return captured["args"]

		self.module.make_address = fake_make_address
		try:
			self.module.create_customer(
				customer_name="RFS POS Customer",
				company="Agile",
				pos_profile_doc='{"posa_allow_duplicate_customer_names": 1}',
				method="create",
				address_line1="1 Test Street",
				city="London",
				country="United Kingdom",
				mobile_no="07123456789",
				email_id="customer@example.com",
			)
		finally:
			self.module.make_address = original_make_address

		self.assertEqual(captured["args"]["phone"], "07123456789")
		self.assertEqual(captured["args"]["email_id"], "customer@example.com")

	def test_get_store_collection_addresses_filters_flagged_addresses(self):
		addresses = self.module.get_store_collection_addresses()

		self.assertEqual(addresses[0]["name"], "STORE-ADDR-1")
		self.assertEqual(
			self.frappe.last_get_all["filters"],
			{"disabled": 0, "posa_is_store_collection_point": 1},
		)

	def test_link_store_collection_address_to_customer_creates_dynamic_link(self):
		self.frappe.db.address_flags["STORE-ADDR-1"] = 1
		self.frappe.db.exists_return_value = False

		result = self.module.link_store_collection_address_to_customer(
			"Customer A", "STORE-ADDR-1"
		)

		self.assertTrue(result["linked"])
		self.assertFalse(result["already_linked"])
		self.assertEqual(
			self.frappe.last_address_doc.links,
			[{"link_doctype": "Customer", "link_name": "Customer A"}],
		)
		self.assertTrue(self.frappe.last_address_doc.saved)

	def test_link_store_collection_address_to_customer_is_idempotent(self):
		self.frappe.db.address_flags["STORE-ADDR-1"] = 1
		self.frappe.db.exists_return_value = True

		result = self.module.link_store_collection_address_to_customer(
			"Customer A", "STORE-ADDR-1"
		)

		self.assertFalse(result["linked"])
		self.assertTrue(result["already_linked"])
		self.assertIsNone(self.frappe.last_address_doc)

	def test_link_store_collection_address_to_customer_rejects_non_store_address(self):
		self.frappe.db.address_flags["STORE-ADDR-1"] = 0

		with self.assertRaisesRegex(Exception, "Selected address is not a store collection point"):
			self.module.link_store_collection_address_to_customer(
				"Customer A", "STORE-ADDR-1"
			)


if __name__ == "__main__":
	unittest.main()
