import importlib.util
import pathlib
import sys
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class _FakeCustomerDoc:
	def __init__(self, payload):
		self.payload = dict(payload)
		self.customer_group = None
		self.territory = None
		self.name = payload.get("customer_name")

	def save(self):
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

			def count(self, doctype, filters):
				self.count_calls.append((doctype, filters))
				return 7

			def exists(self, doctype, filters):
				self.exists_calls.append((doctype, filters))
				return False

		frappe_module.db = _FakeDb()
		frappe_module.last_get_all = None
		frappe_module.last_customer_doc = None

		def fake_get_all(doctype, filters=None, fields=None, order_by=None, limit_start=None, limit_page_length=None):
			frappe_module.last_get_all = {
				"doctype": doctype,
				"filters": filters,
				"fields": fields,
				"order_by": order_by,
				"limit_start": limit_start,
				"limit_page_length": limit_page_length,
			}
			return []

		def fake_get_doc(payload):
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

	def test_get_customer_names_filters_to_rfs_customers(self):
		self.module.get_customer_names('{"customer_groups":[]}', limit=25)

		self.assertEqual(self.frappe.last_get_all["doctype"], "Customer")
		self.assertEqual(
			self.frappe.last_get_all["filters"],
			{"disabled": 0, "rfs_customer": 1},
		)

	def test_get_customers_count_filters_to_rfs_customers(self):
		count = self.module.get_customers_count('{"customer_groups":[]}')

		self.assertEqual(count, 7)
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


if __name__ == "__main__":
	unittest.main()
