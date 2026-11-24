import importlib.util
import pathlib
import sys
import types
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


class AttrDict(dict):
	__getattr__ = dict.get

	def as_dict(self):
		return dict(self)


GET_ALL_CALLS = []
PARTNERS = {"value": None}
ROWS = {"value": None}


def _install_stubs():
	frappe_module = types.ModuleType("frappe")
	frappe_module._ = lambda text: text
	frappe_module.throw = lambda message: (_ for _ in ()).throw(Exception(message))
	frappe_module.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	frappe_module.get_cached_doc = lambda doctype, name: AttrDict(
		{
			"name": name,
			"customer_groups": [{"customer_group": "Retail"}],
			"modified": "2026-04-09T10:02:00",
		}
	)

	def fake_get_all(doctype, **kwargs):
		GET_ALL_CALLS.append((doctype, kwargs))
		if doctype == "Customer" and ROWS["value"] is not None:
			return ROWS["value"]
		if doctype == "Customer":
			return [
				{
					"name": "CUST-REMOVED",
					"modified": "2026-04-09T10:07:00",
					"disabled": 1,
					"customer_group": "Retail",
				},
			]
		return []

	frappe_module.get_all = fake_get_all
	sys.modules["frappe"] = frappe_module

	partner_gate_module = types.ModuleType("posawesome.posawesome.api.partner_gate")
	partner_gate_module.customer_scope_partners = lambda user=None: PARTNERS["value"]
	sys.modules["posawesome.posawesome.api.partner_gate"] = partner_gate_module

	api_utils_module = types.ModuleType("posawesome.posawesome.api.utils")
	api_utils_module.get_active_pos_profile = lambda user=None: {
		"name": "POS-TEST",
		"customer_groups": [{"customer_group": "Retail"}],
		"modified": "2026-04-09T10:02:00",
	}
	sys.modules["posawesome.posawesome.api.utils"] = api_utils_module

	customers_module = types.ModuleType("posawesome.posawesome.api.customers")
	customers_module.get_customer_groups = lambda pos_profile: ["Retail"]
	customers_module.get_customer_names = (
		lambda pos_profile, limit=None, offset=None, start_after=None, modified_after=None: [
			{
				"name": "CUST-001",
				"customer_name": "Alpha Customer",
				"mobile_no": "123",
				"modified": "2026-04-09T10:04:00",
			},
			{
				"name": "CUST-002",
				"customer_name": "Beta Customer",
				"mobile_no": "456",
				"modified": "2026-04-09T10:05:00",
			},
			{
				"name": "CUST-003",
				"customer_name": "Gamma Customer",
				"mobile_no": "789",
				"modified": "2026-04-09T10:06:00",
			},
		][:limit]
	)
	sys.modules["posawesome.posawesome.api.customers"] = customers_module


def _load_module():
	module_name = "test_offline_sync_customers_target"
	file_path = (
		REPO_ROOT
		/ "posawesome"
		/ "posawesome"
		/ "api"
		/ "offline_sync"
		/ "customers.py"
	)
	spec = importlib.util.spec_from_file_location(module_name, file_path)
	module = importlib.util.module_from_spec(spec)
	sys.modules[module_name] = module
	spec.loader.exec_module(module)
	return module


class TestOfflineSyncCustomers(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		_install_stubs()
		cls.module = _load_module()

	def test_sync_customers_returns_delta_changes_and_disabled_deletes(self):
		response = self.module.sync_customers(
			pos_profile="POS-TEST",
			watermark="2026-04-09T09:59:00",
			limit=5,
		)

		self.assertEqual(
			[item["key"] for item in response["changes"]],
			["customer::CUST-001", "customer::CUST-002", "customer::CUST-003"],
		)
		self.assertEqual(response["changes"][1]["data"]["customer_name"], "Beta Customer")
		self.assertEqual(response["deleted"], [{"key": "customer::CUST-REMOVED"}])
		self.assertEqual(response["next_watermark"], "2026-04-09T10:07:00")

	def test_sync_customers_paginates_initial_page_without_watermark(self):
		response = self.module.sync_customers(
			pos_profile="POS-TEST",
			watermark=None,
			limit=2,
		)

		self.assertEqual(
			[item["key"] for item in response["changes"]],
			["customer::CUST-001", "customer::CUST-002"],
		)
		self.assertTrue(response["has_more"])
		self.assertEqual(response["deleted"], [])
		self.assertEqual(response["next_watermark"], "2026-04-09T10:05:00")

	def tearDown(self):
		PARTNERS["value"] = None
		ROWS["value"] = None
		GET_ALL_CALLS.clear()

	def _deleted_filters(self):
		self.module.sync_customers(pos_profile="POS-TEST", watermark="2026-04-09T09:59:00", limit=5)
		return [kwargs["filters"] for doctype, kwargs in GET_ALL_CALLS if doctype == "Customer"][-1]

	def test_deleted_customers_are_not_partner_scoped_for_normal_users(self):
		self.assertNotIn("default_sales_partner", self._deleted_filters())

	def test_deleted_customers_are_limited_to_the_partners_customers(self):
		PARTNERS["value"] = ["SP-A"]
		self.assertEqual(self._deleted_filters()["default_sales_partner"], ["in", ["SP-A"]])

	NON_RFS_ROW = {
		"name": "AGILE-CUST",
		"modified": "2026-04-09T10:08:00",
		"disabled": 0,
		"customer_group": "Retail",
		"rfs_customer": 0,
	}

	def test_non_rfs_customer_is_reported_deleted_for_staff(self):
		ROWS["value"] = [self.NON_RFS_ROW]
		response = self.module.sync_customers(pos_profile="POS-TEST", watermark="2026-04-09T09:59:00", limit=5)
		self.assertEqual(response["deleted"], [{"key": "customer::AGILE-CUST"}])

	def test_partners_non_rfs_customer_is_not_reported_deleted(self):
		# Partner customers are Agile-side, deliberately not RFS.
		PARTNERS["value"] = ["SP-A"]
		ROWS["value"] = [self.NON_RFS_ROW]
		response = self.module.sync_customers(pos_profile="POS-TEST", watermark="2026-04-09T09:59:00", limit=5)
		self.assertEqual(response["deleted"], [])

	def test_partners_disabled_customer_is_still_reported_deleted(self):
		PARTNERS["value"] = ["SP-A"]
		ROWS["value"] = [{**self.NON_RFS_ROW, "disabled": 1}]
		response = self.module.sync_customers(pos_profile="POS-TEST", watermark="2026-04-09T09:59:00", limit=5)
		self.assertEqual(response["deleted"], [{"key": "customer::AGILE-CUST"}])


if __name__ == "__main__":
	unittest.main()
