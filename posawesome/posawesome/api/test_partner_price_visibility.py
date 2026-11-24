"""Real-site check (test_agile) that a partner's single-price lookups only see rows they may.

Runs through ``cdd_run_one.py``-style direct unittest on a site with customer_due_dates
installed; everything is rolled back.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from posawesome.posawesome.api.item_processing.barcode import get_items_from_barcode
from posawesome.posawesome.api.item_processing.price import get_price_for_uom

ROLE = "POS Sales Partner"


class TestPartnerPriceVisibility(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		h = frappe.generate_hash(length=6)
		self.h = h
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")

		self.own_list = self._price_list(f"WP4T Own {h}", selling=1)
		self.buying_list = self._price_list(f"WP4T Buy {h}", selling=0)
		self.user = f"wp4t{h}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.user,
				"first_name": "WP4T",
				"send_welcome_email": 0,
				"roles": [{"role": ROLE}],
			}
		).insert(ignore_permissions=True)
		self.partner = frappe.get_doc(
			{
				"doctype": "Sales Partner",
				"partner_name": f"WP4T SP {h}",
				"commission_rate": 5,
				"territory": territory,
				"portal_users": [{"user": self.user}],
			}
		).insert(ignore_permissions=True)
		other_partner = frappe.get_doc(
			{
				"doctype": "Sales Partner",
				"partner_name": f"WP4T SP2 {h}",
				"commission_rate": 5,
				"territory": territory,
			}
		).insert(ignore_permissions=True)

		def customer(name, partner):
			return frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_group": group,
					"territory": territory,
					"default_price_list": self.own_list,
					"default_sales_partner": partner.name,
				}
			).insert(ignore_permissions=True)

		# "ZZ" sorts after the in-scope name, so a missing customer filter returns it first.
		self.mine = customer(f"WP4T Mine {h}", self.partner)
		self.foreign = customer(f"ZZ WP4T Foreign {h}", other_partner)
		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"WP4T-ITEM-{h}",
				"item_name": f"WP4T item {h}",
				"item_group": item_group,
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"barcodes": [{"barcode": f"WP4T{h}"}],
			}
		).insert(ignore_permissions=True)
		for column, value in (("custom_tfw_price", 99), ("pos_on_sale_price", 88)):
			if frappe.db.has_column("Item", column):
				frappe.db.set_value("Item", self.item.name, column, value)
		frappe.clear_document_cache("Item", self.item.name)

	def _price_list(self, name, selling):
		return frappe.get_doc(
			{
				"doctype": "Price List",
				"price_list_name": name,
				"currency": "GBP",
				"selling": selling,
				"buying": 0 if selling else 1,
				"enabled": 1,
			}
		).insert(ignore_permissions=True).name

	def _price(self, rate, customer=None, price_list=None):
		return frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": self.item.name,
				"price_list": price_list or self.own_list,
				"price_list_rate": rate,
				"uom": "Nos",
				"currency": "GBP",
				"selling": 1,
				"customer": customer,
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")

	def as_partner(self, fn, *args):
		frappe.clear_cache(user=self.user)
		frappe.set_user(self.user)
		try:
			return fn(*args)
		finally:
			frappe.set_user("Administrator")

	def test_partner_never_reads_another_customers_price_row(self):
		self._price(10)  # list-wide
		self._price(999, customer=self.foreign.name)
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, self.own_list, "Nos", self.mine.name), 10)

		self._price(12, customer=self.mine.name)
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, self.own_list, "Nos", self.mine.name), 12)

	def test_partner_sees_nothing_when_only_a_foreign_row_exists(self):
		self._price(999, customer=self.foreign.name)
		self.assertIsNone(self.as_partner(get_price_for_uom, self.item.name, self.own_list, "Nos", self.mine.name))

	def test_staff_still_read_any_row(self):
		self._price(999, customer=self.foreign.name)
		self.assertEqual(get_price_for_uom(self.item.name, self.own_list, "Nos"), 999)

	def test_partner_is_priced_from_the_customer_never_a_buying_list_they_name(self):
		self._price(5, price_list=self.buying_list)
		self._price(10)
		# The browser's list is ignored: the customer's own list answers.
		self.assertEqual(
			self.as_partner(get_price_for_uom, self.item.name, self.buying_list, "Nos", self.mine.name), 10
		)
		row = self.as_partner(get_items_from_barcode, self.buying_list, "GBP", f"WP4T{self.h}", self.mine.name)
		self.assertEqual(row["price_list_rate"], 10)
		# Another partner's customer is refused, and so is a call with no customer.
		with self.assertRaises(frappe.PermissionError):
			self.as_partner(get_price_for_uom, self.item.name, self.own_list, "Nos", self.foreign.name)
		# Staff are unchanged.
		self.assertEqual(get_price_for_uom(self.item.name, self.buying_list, "Nos"), 5)

	def test_barcode_prices_a_partner_from_the_list_only(self):
		self._price(10)
		self._price(999, customer=self.foreign.name)
		row = self.as_partner(get_items_from_barcode, self.own_list, "GBP", f"WP4T{self.h}", self.mine.name)
		self.assertEqual(row["item_code"], self.item.name)
		self.assertEqual(row["price_list_rate"], 10)
		self.assertEqual((row["custom_tfw_price"], row["pos_on_sale_price"], row["is_on_sale"]), (0, 0, False))

		if frappe.db.has_column("Item", "custom_tfw_price"):
			staff = get_items_from_barcode(self.own_list, "GBP", f"WP4T{self.h}")
			self.assertEqual(staff["custom_tfw_price"], 99, "staff keep the TFW price")
