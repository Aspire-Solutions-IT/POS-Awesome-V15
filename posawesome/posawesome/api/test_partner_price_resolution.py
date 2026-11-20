"""Real-site checks (test_agile) of the partner price resolver and everything that uses it.

Direct unittest run on a site with customer_due_dates installed (see
``test_partner_price_visibility``). Everything is created inside the test transaction and
rolled back. Covers WP4 review findings H1 (supplier rows), H2 (one charge/fallback
resolution), H3 (item details write nothing), M1 (UOM / barcode quote what the order
charges), M2 (offline deltas) and M3 (price list metadata scope).
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from posawesome.posawesome.api import charge_pricing, partner_pricing
from posawesome.posawesome.api import items as items_api
from posawesome.posawesome.api.invoice_processing.utils import get_price_list_currency
from posawesome.posawesome.api.item_fetchers import _fetch_item_prices
from posawesome.posawesome.api.item_processing.barcode import get_items_from_barcode
from posawesome.posawesome.api.item_processing.details import get_item_detail
from posawesome.posawesome.api.item_processing.price import get_price_for_uom
from posawesome.posawesome.api.partner_gate import allowed_price_lists, get_scope

ROLE = "POS Sales Partner"
P = "WP4F"


class TestPartnerPriceResolution(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.flags.pop("posa_items_stub", None)
		h = self.h = frappe.generate_hash(length=6)
		self.company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
		territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
		group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")

		self.own = self._list(f"{P} Own {h}")
		self.fallback = self._list(f"{P} Fallback {h}")
		self.dual = self._list(f"{P} Dual {h}", buying=1)
		self.buying = self._list(f"{P} Buy {h}", selling=0, buying=1)
		self.locked_list = self._list(f"{P} Locked {h}")
		self.charge_list = self._list(f"{P} ChargeList {h}")
		frappe.db.set_value("Price List", self.own, "fallback_price_list", self.fallback)

		self.user = f"wp4f{h}@example.com"
		frappe.get_doc(
			{"doctype": "User", "email": self.user, "first_name": P, "send_welcome_email": 0, "roles": [{"role": ROLE}]}
		).insert(ignore_permissions=True)
		self.partner = frappe.get_doc(
			{
				"doctype": "Sales Partner",
				"partner_name": f"{P} SP {h}",
				"commission_rate": 5,
				"territory": territory,
				"portal_users": [{"user": self.user}],
			}
		).insert(ignore_permissions=True)
		other_partner = frappe.get_doc(
			{"doctype": "Sales Partner", "partner_name": f"{P} SP2 {h}", "commission_rate": 5, "territory": territory}
		).insert(ignore_permissions=True)

		def customer(name, partner, price_list):
			return frappe.get_doc(
				{
					"doctype": "Customer",
					"customer_name": name,
					"customer_group": group,
					"territory": territory,
					"default_price_list": price_list,
					"default_sales_partner": partner.name,
				}
			).insert(ignore_permissions=True)

		self.mine = customer(f"{P} Mine {h}", self.partner, self.own)
		self.mine2 = customer(f"{P} Mine2 {h}", self.partner, self.own)
		self.foreign = customer(f"{P} Foreign {h}", other_partner, self.own)
		self.nolist = customer(f"{P} NoList {h}", self.partner, None)

		self.item = frappe.get_doc(
			{
				"doctype": "Item",
				"item_code": f"{P}-ITEM-{h}",
				"item_name": f"{P} item {h}",
				"item_group": item_group,
				"stock_uom": "Nos",
				"is_stock_item": 0,
				"uoms": [{"uom": "Nos", "conversion_factor": 1}, {"uom": "Box", "conversion_factor": 6}],
				"barcodes": [{"barcode": f"{P}{h}", "posa_uom": "Box"}],
			}
		).insert(ignore_permissions=True)
		self.supplier = frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": f"{P} Supplier {h}", "supplier_group": frappe.db.get_value("Supplier Group", {}, "name")}
		).insert(ignore_permissions=True)

	# --- fixtures -------------------------------------------------------------------
	def _list(self, name, selling=1, buying=0, enabled=1, currency="GBP"):
		return (
			frappe.get_doc(
				{
					"doctype": "Price List",
					"price_list_name": name,
					"currency": currency,
					"selling": selling,
					"buying": buying,
					"enabled": enabled,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _price(self, rate, price_list, uom="Nos", customer=None, supplier=None, **kw):
		doc = frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": self.item.name,
				"price_list": price_list,
				"price_list_rate": rate,
				"uom": uom,
				"currency": "GBP",
				"customer": customer,
				"supplier": supplier,
				**kw,
			}
		)
		return doc.insert(ignore_permissions=True)

	def _charge(self, label, **kw):
		values = {
			"doctype": "Delivery Charges",
			"label": f"{P} {label} {self.h}",
			"company": self.company,
			"shipping_account": frappe.db.get_value("Account", {"company": self.company, "is_group": 0, "root_type": "Expense"}, "name"),
			"cost_center": frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name"),
			"default_rate": 10,
			"available_to": "Agile only",
		}
		values.update(kw)
		return frappe.get_doc(values).insert(ignore_permissions=True).name

	def as_partner(self, fn, *args, **kwargs):
		frappe.clear_cache(user=self.user)
		frappe.set_user(self.user)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")

	# --- H1 ---------------------------------------------------------------------------
	def test_h1_dual_purpose_list_generic_row_is_visible_supplier_row_is_not(self):
		frappe.db.set_value("Customer", self.mine.name, "default_price_list", self.dual)
		self._price(40, self.dual, supplier=self.supplier.name)  # a supplier's negotiated rate
		self.assertIsNone(
			self.as_partner(get_price_for_uom, self.item.name, self.dual, "Nos", self.mine.name),
			"only a supplier-specific row exists: invisible",
		)
		self._price(70, self.dual)  # generic dual-purpose row: no supplier, no customer
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, self.dual, "Nos", self.mine.name), 70)

	def test_h1_bulk_resolver_applies_the_same_row_filter(self):
		self._price(40, self.dual, supplier=self.supplier.name)
		self._price(70, self.dual)
		args = (self.dual, "GBP", (self.item.name,), "", nowdate())
		partner_rows = _fetch_item_prices(*args, True)
		self.assertEqual([r.price_list_rate for r in partner_rows], [70])
		# Staff keep seeing everything they did.
		self.assertEqual(sorted(r.price_list_rate for r in _fetch_item_prices(*args)), [40, 70])

	def test_h1_a_buying_only_row_on_an_own_list_is_never_a_selling_price(self):
		row = self._price(5, self.own)
		frappe.db.set_value("Item Price", row.name, "selling", 0)
		self.assertEqual(_fetch_item_prices(self.own, "GBP", (self.item.name,), "", nowdate(), True), [])

	# --- H2 ---------------------------------------------------------------------------
	def test_h2_a_disabled_or_staff_only_charge_is_refused_before_any_price_read(self):
		disabled = self._charge("Disabled", price_list=self.charge_list, disabled=1)
		staff_only = self._charge("Staff", price_list=self.charge_list, available_to="TFW only")
		for name in (disabled, staff_only):
			with self.assertRaises(frappe.PermissionError, msg=name):
				self.as_partner(partner_pricing.resolve_pricing_context, self.mine.name, name)

	def test_h2_charge_for_another_company_is_refused(self):
		other = frappe.db.get_value("Company", {"name": ["!=", self.company]}, "name")
		if not other:
			self.skipTest("one company only")
		name = self._charge("OtherCo", price_list=self.charge_list, company=other)
		with self.assertRaises(frappe.PermissionError):
			self.as_partner(partner_pricing.resolve_pricing_context, self.mine.name, name)

	def test_h2_buying_only_fallback_list_is_never_used_at_any_step(self):
		frappe.db.set_value("Price List", self.own, "fallback_price_list", self.buying)
		self._price(5, self.buying)
		ctx = self.as_partner(partner_pricing.resolve_pricing_context, self.mine.name)
		self.assertIsNone(ctx.fallback)
		# A charge whose own list is buying-only cannot be the fallback either.
		frappe.db.set_value("Price List", self.own, "fallback_price_list", None)
		name = self._charge("BuyCharge", price_list=self.buying)
		ctx = self.as_partner(partner_pricing.resolve_pricing_context, self.mine.name, name)
		self.assertIsNone(ctx.fallback)
		self.assertNotIn(self.buying, self.as_partner(lambda: allowed_price_lists(get_scope()["partners"])))

	def test_h2_locked_charge_prices_from_its_own_list_and_never_falls_back(self):
		frappe.db.set_value("Price List", self.locked_list, "fallback_price_list", self.fallback)
		name = self._charge("Locked", price_list=self.locked_list, price_list_overrides_customer=1)
		ctx = self.as_partner(partner_pricing.resolve_pricing_context, self.mine.name, name)
		self.assertEqual((ctx.price_list, ctx.fallback), (self.locked_list, None))

	def test_h2_gate_and_resolver_agree(self):
		std = self._charge("Std", price_list=self.charge_list)
		locked = self._charge("Locked", price_list=self.locked_list, price_list_overrides_customer=1)
		allowed = self.as_partner(lambda: allowed_price_lists(get_scope()["partners"]))
		for charge in (None, std, locked):
			for customer in (self.mine, self.nolist):
				try:
					ctx = self.as_partner(partner_pricing.resolve_pricing_context, customer.name, charge)
				except frappe.ValidationError:
					continue  # no list for this customer: the resolver refuses
				for name in (ctx.price_list, ctx.fallback):
					if name:
						self.assertIn(name, allowed, (charge, customer.name, name))
		self.assertNotIn(self.buying, allowed)
		self.assertNotIn(self.dual, allowed)  # nobody's list

	def test_h2_charge_only_customer_resolves_through_the_charge(self):
		std = self._charge("Std", price_list=self.charge_list)
		ctx = self.as_partner(partner_pricing.resolve_pricing_context, self.nolist.name, std)
		self.assertEqual(ctx.price_list, self.charge_list)

	# --- H3 ---------------------------------------------------------------------------
	def _auto_insert_on(self):
		settings = frappe.get_doc("Stock Settings")
		settings.auto_insert_price_list_rate_if_missing = 1
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

	def test_h3_partner_item_detail_creates_no_item_price(self):
		self._auto_insert_on()
		self._price(33, self.fallback)  # priced only on the fallback: succeeds with the old code too
		before = frappe.db.count("Item Price")
		result = self.as_partner(
			get_item_detail,
			{
				"item_code": self.item.name,
				"qty": 1,
				"uom": "Nos",
				"rate": 55,
				"price_list_rate": 55,
				"price_list": self.buying,
				"currency": "GBP",
				"supplier": self.supplier.name,
				"customer": self.mine.name,
				"plc_conversion_rate": 1,
			},
			None,
			None,
			self.buying,
			self.company,
		)
		self.assertEqual(frappe.db.count("Item Price"), before, "no Item Price row may be created")
		self.assertEqual(result["price_list_rate"], 33)
		self.assertEqual(result["selling_price_list"], self.own)

	def test_h3_staff_path_still_runs_unchanged(self):
		self._price(33, self.own)
		result = get_item_detail(
			{"item_code": self.item.name, "qty": 1, "uom": "Nos", "customer": self.mine.name, "currency": "GBP"},
			None,
			None,
			self.own,
			self.company,
		)
		self.assertEqual(result["price_list_rate"], 33)

	# --- M1 ---------------------------------------------------------------------------
	def test_m1_uom_rate_is_the_selected_customers_not_a_siblings(self):
		self._price(10, self.own)
		self._price(8, self.own, customer=self.mine.name)
		self._price(7, self.own, customer=self.mine2.name)
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, "ignored", "Nos", self.mine.name), 8)
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, "ignored", "Nos", self.mine2.name), 7)

	def test_m1_future_and_expired_rows_are_not_quoted(self):
		self._price(10, self.own)
		self._price(1, self.own, valid_from=add_days(nowdate(), 5))
		self._price(2, self.own, valid_from=add_days(nowdate(), -20), valid_upto=add_days(nowdate(), -10))
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, self.own, "Nos", self.mine.name), 10)

	def test_m1_uom_scales_the_stock_price_and_prefers_an_exact_row(self):
		self._price(10, self.own)
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, self.own, "Box", self.mine.name), 60)
		self._price(50, self.own, uom="Box")
		self.assertEqual(self.as_partner(get_price_for_uom, self.item.name, self.own, "Box", self.mine.name), 50)

	def test_m1_uom_follows_the_charge_and_ignores_the_browsers_list(self):
		self._price(10, self.own)
		self._price(99, self.locked_list)
		locked = self._charge("Locked", price_list=self.locked_list, price_list_overrides_customer=1)
		rate = self.as_partner(get_price_for_uom, self.item.name, self.buying, "Nos", self.mine.name, locked)
		self.assertEqual(rate, 99)

	def test_m1_uom_for_another_partners_customer_is_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self.as_partner(get_price_for_uom, self.item.name, self.own, "Nos", self.foreign.name)

	def test_m1_barcode_prices_the_barcodes_uom_and_ignores_scale_prices(self):
		self._price(10, self.own)
		self._price(55, self.own, uom="Box")
		row = self.as_partner(
			get_items_from_barcode, self.buying, "GBP", f"{P}{self.h}", self.mine.name, None
		)
		self.assertEqual((row["uom"], row["price_list_rate"]), ("Box", 55))
		self.assertIsNone(row["scale_price"])

	def test_m1_a_scale_barcodes_encoded_price_is_not_a_partners_price(self):
		from posawesome.posawesome.api.item_processing import barcode as barcode_module

		self._price(10, self.own)
		original = barcode_module._parse_scale_barcode_data
		barcode_module._parse_scale_barcode_data = lambda code: {"item_code": self.item.name, "qty": 2, "price": 1.5}
		try:
			row = self.as_partner(get_items_from_barcode, self.own, "GBP", "2000000", self.mine.name, None)
			staff = get_items_from_barcode(self.own, "GBP", "2000000")
		finally:
			barcode_module._parse_scale_barcode_data = original
		self.assertEqual((row["price_list_rate"], row["scale_price"]), (10, None))
		self.assertEqual(staff["scale_price"], 1.5, "staff keep scale prices")

	def test_m1_barcode_for_another_customer_or_no_customer_is_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self.as_partner(get_items_from_barcode, self.own, "GBP", f"{P}{self.h}", self.foreign.name)
		with self.assertRaises(frappe.ValidationError):  # "Select a customer first."
			self.as_partner(get_items_from_barcode, self.own, "GBP", f"{P}{self.h}", None)

	# --- M2 ---------------------------------------------------------------------------
	def test_m2_delta_codes_follow_the_resolved_lists_and_row_visibility(self):
		self._price(10, self.fallback)
		other_item = frappe.get_doc(
			{"doctype": "Item", "item_code": f"{P}-OTHER-{self.h}", "item_name": "o", "item_group": self.item.item_group, "stock_uom": "Nos", "is_stock_item": 0}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "Item Price", "item_code": other_item.name, "price_list": self.own, "price_list_rate": 3, "currency": "GBP", "customer": self.foreign.name}
		).insert(ignore_permissions=True)
		before = frappe.utils.get_datetime(add_days(nowdate(), -1))
		codes = items_api._collect_delta_item_codes(
			frappe._dict(), before, [self.own, self.fallback], 100, partner_customer=self.mine.name
		)
		self.assertIn(self.item.name, codes, "a fallback-list price change is picked up")
		self.assertNotIn(other_item.name, codes, "another customer's row is not")
		# Staff are unchanged: they see the list's rows, whoever they belong to.
		staff_codes = items_api._collect_delta_item_codes(frappe._dict(), before, self.own, 100)
		self.assertIn(other_item.name, staff_codes)

	def test_m2_delta_resolves_the_customer_through_the_charge(self):
		std = self._charge("Std", price_list=self.charge_list)
		seen = {}

		def fake_get_items(profile_json, price_list=None, **kw):
			seen["price_list"] = price_list
			return []

		frappe.db.set_value("Price List", self.charge_list, "fallback_price_list", self.fallback)
		collected = {}

		def fake_collect(profile, modified_after, price_lists, limit, partner_customer=None):
			collected["lists"], collected["customer"] = list(price_lists), partner_customer
			return set()

		original = items_api.get_items
		original_collect = items_api._collect_delta_item_codes
		items_api.get_items = fake_get_items
		items_api._collect_delta_item_codes = fake_collect
		def call():
			frappe.form_dict["delivery_charge"] = std  # the browser's charge, as chargeRequestArgs sends it
			return items_api.get_delta_items(
				frappe.as_json({"name": "X", "warehouse": None}),
				add_days(nowdate(), -1) + "T00:00:00",
				None,
				self.nolist.name,
			)

		try:
			self.as_partner(call)
		finally:
			items_api.get_items = original
			items_api._collect_delta_item_codes = original_collect
			frappe.form_dict.pop("delivery_charge", None)
		self.assertEqual(collected["lists"], [self.charge_list, self.fallback], "the grid's primary and fallback")
		self.assertEqual(collected["customer"], self.nolist.name)
		self.assertEqual(seen["price_list"], self.charge_list)

	# --- M3 ---------------------------------------------------------------------------
	def test_m3_price_list_currency_is_scoped_for_a_partner(self):
		self.assertEqual(self.as_partner(get_price_list_currency, self.own), "GBP")
		# Outside the scope: no metadata, and no error that would break POS load.
		profile, _company = charge_pricing.server_profile_context(self.user)
		expected = (frappe.db.get_value("POS Profile", profile, "currency") if profile else None) or None
		for name in (self.buying, self.dual, self.locked_list):
			self.assertEqual(self.as_partner(get_price_list_currency, name), expected, name)
		# Staff are unchanged.
		self.assertEqual(get_price_list_currency(self.buying), "GBP")

	def test_m3_selling_price_lists_for_a_partner_are_only_theirs(self):
		from posawesome.posawesome.api.utilities import get_selling_price_lists

		names = {r["name"] for r in self.as_partner(get_selling_price_lists)}
		self.assertIn(self.own, names)
		self.assertTrue(names.isdisjoint({self.buying, self.dual, self.locked_list}))
