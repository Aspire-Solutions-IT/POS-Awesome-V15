import importlib.util
import pathlib
import sys
import types
import unittest

API_DIR = pathlib.Path(__file__).resolve().parent


class FakePermissionError(Exception):
    pass


class _dict(dict):
    __getattr__ = dict.get


class Row(types.SimpleNamespace):
    """A Sales Order Item: attribute access plus the .get/.set a Document row has."""

    def get(self, key, default=None):
        return getattr(self, key, default)

    def set(self, key, value):
        setattr(self, key, value)


class Doc(types.SimpleNamespace):
    def __init__(self, **kw):
        kw.setdefault("docstatus", 0)
        kw.setdefault("_action", "save")
        super().__init__(**kw)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def remove(self, row):
        self.items.remove(row)


# State the fakes read; reset per test.
STATE = {}


def _install():
    names = [
        "frappe",
        "frappe.utils",
        "frappe.utils.caching",
        "frappe.query_builder",
        "frappe.query_builder.functions",
        "erpnext",
        "erpnext.setup",
        "erpnext.setup.utils",
    ]
    saved = {name: sys.modules.get(name) for name in names}

    frappe = types.ModuleType("frappe")
    frappe.PermissionError = FakePermissionError
    frappe._ = lambda text: text
    frappe._dict = _dict
    frappe.session = types.SimpleNamespace(user="partner@example.com")
    frappe.get_hooks = lambda key: ["x.scope"] if STATE.get("partner") else []
    frappe.get_attr = lambda path: lambda user: {"is_partner": True, "partners": ["SP-A"]}
    frappe.set_user = lambda user: setattr(frappe.session, "user", user)

    def throw(msg, exc=Exception):
        raise exc(msg)

    def get_value(doctype, name, fieldname):
        table = STATE["values"].get((doctype, name))
        if table is None:
            return None
        if isinstance(fieldname, (list, tuple)):
            return tuple(table.get(f) for f in fieldname)
        return table.get(fieldname)

    frappe.throw = throw
    frappe.db = types.SimpleNamespace(get_value=get_value, has_column=lambda *a: True)

    utils = types.ModuleType("frappe.utils")
    utils.cint = lambda v=0: int(v or 0)
    utils.flt = lambda v=0, *a, **k: float(v or 0)
    utils.nowdate = lambda: "2026-11-10"
    caching = types.ModuleType("frappe.utils.caching")
    caching.redis_cache = lambda **kw: (lambda fn: fn)
    qb = types.ModuleType("frappe.query_builder")
    qb.DocType = object
    qbf = types.ModuleType("frappe.query_builder.functions")
    qbf.Sum = object
    erp = types.ModuleType("erpnext")
    erp_setup = types.ModuleType("erpnext.setup")
    erp_utils = types.ModuleType("erpnext.setup.utils")
    erp_utils.get_exchange_rate = lambda *a, **k: 1

    for name, mod in {
        "frappe": frappe,
        "frappe.utils": utils,
        "frappe.utils.caching": caching,
        "frappe.query_builder": qb,
        "frappe.query_builder.functions": qbf,
        "erpnext": erp,
        "erpnext.setup": erp_setup,
        "erpnext.setup.utils": erp_utils,
    }.items():
        sys.modules[name] = mod
    frappe.utils = utils

    def load(module_name, filename):
        spec = importlib.util.spec_from_file_location(module_name, API_DIR / filename)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    # Package shells so the modules' relative imports resolve to the files under test.
    pkg_root = types.ModuleType("posawesome")
    pkg_root.__path__ = []
    pkg = types.ModuleType("posawesome.posawesome")
    pkg.__path__ = []
    api = types.ModuleType("posawesome.posawesome.api")
    api.__path__ = [str(API_DIR)]
    for name, mod in {
        "posawesome": pkg_root,
        "posawesome.posawesome": pkg,
        "posawesome.posawesome.api": api,
    }.items():
        sys.modules[name] = mod

    gate = load("posawesome.posawesome.api.partner_gate", "partner_gate.py")
    api.partner_gate = gate
    fetchers = load("posawesome.posawesome.api.item_fetchers", "item_fetchers.py")
    api.item_fetchers = fetchers
    pricing = load("posawesome.posawesome.api.partner_pricing", "partner_pricing.py")
    api.partner_pricing = pricing

    # Leave no stub behind for other test files.
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod
    return gate, fetchers, pricing, frappe


GATE, FETCHERS, PRICING, FRAPPE = _install()


def _values(**overrides):
    values = {
        ("Customer", "CUST-A"): {
            "default_sales_partner": "SP-A",
            "default_price_list": "Trade GBP",
            "default_commission_rate": 0,
        },
        ("Customer", "CUST-B"): {"default_sales_partner": "SP-B", "default_price_list": "Trade GBP"},
        ("Customer", "CUST-NOLIST"): {"default_sales_partner": "SP-A", "default_price_list": None},
        ("Price List", "Trade GBP"): {"enabled": 1, "selling": 1, "currency": "GBP"},
        ("Sales Partner", "SP-A"): {"commission_rate": 5},
        ("Price List", "Off"): {"enabled": 0, "selling": 1, "currency": "GBP"},
        ("Item", "WIDGET"): {"stock_uom": "Nos"},
    }
    values.update(overrides)
    return values


def _price_rows(*rows):
    return [_dict(item_code="WIDGET", currency="GBP", customer="", **row) for row in rows]


class Base(unittest.TestCase):
    def setUp(self):
        STATE.clear()
        STATE.update(partner=True, values=_values(), prices=_price_rows({"price_list_rate": 50, "uom": "Nos"}))
        self._orig = PRICING.__dict__.get("_fetch")
        self.fetch_calls = []

        def fake_fetch(price_list, currency, item_codes, customer, today):
            self.fetch_calls.append((price_list, currency, item_codes, customer))
            return STATE["prices"]

        self._orig_fetch = FETCHERS._fetch_item_prices
        FETCHERS._fetch_item_prices = fake_fetch
        # Bind the module globals the code under test reads to this test's fakes.
        self._saved = {}
        for module in (GATE, PRICING):
            self._saved[module] = module.frappe
            module.frappe = FRAPPE

    def tearDown(self):
        FETCHERS._fetch_item_prices = self._orig_fetch
        for module, frappe in self._saved.items():
            module.frappe = frappe


class TestPriceList(Base):
    def test_customer_needs_a_default_price_list(self):
        self.assertEqual(PRICING.get_customer_price_list("CUST-A"), "Trade GBP")
        with self.assertRaisesRegex(Exception, "no default price list"):
            PRICING.get_customer_price_list("CUST-NOLIST")
        with self.assertRaisesRegex(Exception, "Select a customer"):
            PRICING.get_customer_price_list(None)

    def test_price_list_must_be_an_enabled_selling_list(self):
        STATE["values"][("Customer", "CUST-A")]["default_price_list"] = "Off"
        with self.assertRaisesRegex(Exception, "not an enabled selling"):
            PRICING.get_customer_price_list("CUST-A")

    def test_customer_must_be_in_scope(self):
        self.assertEqual(PRICING.require_scoped_customer("CUST-A"), "CUST-A")
        for customer in ("CUST-B", "CUST-MISSING"):
            with self.subTest(customer=customer), self.assertRaises(FakePermissionError):
                PRICING.require_scoped_customer(customer)

    def test_missing_customer_is_a_friendly_error_not_a_permission_error(self):
        with self.assertRaisesRegex(Exception, "Select a customer first") as ctx:
            PRICING.require_scoped_customer(None)
        self.assertNotIsInstance(ctx.exception, FakePermissionError)


class TestRate(Base):
    def test_exact_uom_row(self):
        STATE["prices"] = _price_rows({"price_list_rate": 50, "uom": "Nos"}, {"price_list_rate": 270, "uom": "Box"})
        self.assertEqual(PRICING.get_price_list_rate("WIDGET", "Trade GBP", "Box", 6), 270)

    def test_other_uom_scales_the_stock_price(self):
        self.assertEqual(PRICING.get_price_list_rate("WIDGET", "Trade GBP", "Box", 6), 300)
        self.assertEqual(PRICING.get_price_list_rate("WIDGET", "Trade GBP", "Nos", 1), 50)
        self.assertEqual(PRICING.get_price_list_rate("WIDGET", "Trade GBP", None, None), 50)

    def test_no_price_is_none(self):
        STATE["prices"] = []
        self.assertIsNone(PRICING.get_price_list_rate("WIDGET", "Trade GBP", "Nos", 1))

    def test_price_list_currency_and_customer_are_passed_through(self):
        PRICING.get_price_list_rate("WIDGET", "Trade GBP", "Nos", 1, customer="CUST-A")
        self.assertEqual(self.fetch_calls[0], ("Trade GBP", "GBP", ("WIDGET",), "CUST-A"))

    def test_later_customer_specific_row_wins(self):
        STATE["prices"] = [
            _dict(item_code="WIDGET", currency="GBP", customer="", price_list_rate=50, uom="Nos"),
            _dict(item_code="WIDGET", currency="GBP", customer="CUST-A", price_list_rate=42, uom="Nos"),
        ]
        self.assertEqual(PRICING.get_price_list_rate("WIDGET", "Trade GBP", "Nos", 1, "CUST-A"), 42)


class TestSalesOrderHook(Base):
    def _doc(self, **kw):
        items = kw.pop("items", None) or [
            Row(idx=1, item_code="WIDGET", uom="Nos", conversion_factor=1, rate=0, price_list_rate=0,
                discount_percentage=30, discount_amount=5, margin_rate_or_amount=9, pricing_rules="X")
        ]
        return Doc(customer="CUST-A", items=items, selling_price_list="Standard Selling",
                   ignore_pricing_rule=0, additional_discount_percentage=15, discount_amount=20,
                   coupon_code="SAVE", **kw)

    def test_non_partner_is_untouched(self):
        STATE["partner"] = False
        doc = self._doc()
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.selling_price_list, "Standard Selling")
        self.assertEqual(doc.items[0].rate, 0)
        self.assertEqual(doc.discount_amount, 20)

    def test_tampered_order_is_repriced_from_the_customers_list(self):
        doc = self._doc()
        PRICING.enforce_sales_order_pricing(doc)
        row = doc.items[0]
        self.assertEqual(doc.selling_price_list, "Trade GBP")
        # The rate comes from the list and the client's 30% discount; never the client's rate.
        self.assertEqual((row.rate, row.price_list_rate, row.discount_percentage), (35.0, 50, 30))
        self.assertEqual((row.discount_amount, row.margin_rate_or_amount), (0, 0))
        self.assertEqual(row.pricing_rules, "")
        self.assertEqual((doc.ignore_pricing_rule, doc.coupon_code), (1, ""))
        # Order-level discounts within the cap are kept, taken off the net total.
        self.assertEqual((doc.additional_discount_percentage, doc.discount_amount), (15, 20))
        self.assertEqual(doc.apply_discount_on, "Net Total")

    def test_a_high_client_rate_is_also_overwritten(self):
        doc = self._doc(items=[Row(idx=1, item_code="WIDGET", uom="Nos", conversion_factor=1, rate=999, price_list_rate=999)])
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.items[0].rate, 50)

    def test_uom_conversion_is_applied(self):
        doc = self._doc(items=[Row(idx=1, item_code="WIDGET", uom="Box", conversion_factor=6, rate=1, price_list_rate=1)])
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.items[0].rate, 300)

    def test_free_items_are_removed(self):
        free = Row(idx=2, item_code="WIDGET", uom="Nos", conversion_factor=1, is_free_item=1, rate=0)
        paid = Row(idx=1, item_code="WIDGET", uom="Nos", conversion_factor=1, rate=1, price_list_rate=1)
        doc = self._doc(items=[paid, free])
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.items, [paid])

    def test_unpriced_item_is_rejected(self):
        STATE["prices"] = []
        with self.assertRaisesRegex(Exception, "Row 1: WIDGET has no price on price list Trade GBP"):
            PRICING.enforce_sales_order_pricing(self._doc())

    def test_zero_price_counts_as_unpriced(self):
        STATE["prices"] = _price_rows({"price_list_rate": 0, "uom": "Nos"})
        with self.assertRaisesRegex(Exception, "no price"):
            PRICING.enforce_sales_order_pricing(self._doc())

    def test_customer_without_price_list_is_rejected(self):
        with self.assertRaisesRegex(Exception, "no default price list"):
            PRICING.enforce_sales_order_pricing(self._doc(**{}) if False else Doc(
                customer="CUST-NOLIST", items=[Row(idx=1, item_code="WIDGET", uom="Nos", conversion_factor=1)]
            ))

    def test_other_partners_customer_is_rejected(self):
        doc = self._doc()
        doc.customer = "CUST-B"
        with self.assertRaises(FakePermissionError):
            PRICING.enforce_sales_order_pricing(doc)

    def test_edits_after_submit_and_cancelled_docs_are_skipped(self):
        doc = self._doc(); doc._action = "update_after_submit"
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.items[0].rate, 0)
        doc = self._doc(); doc.docstatus = 2
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.items[0].rate, 0)

    def test_submit_action_is_repriced_too(self):
        doc = self._doc(); doc.docstatus = 1; doc._action = "submit"
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.items[0].rate, 35.0)


class TestDiscountCap(Base):
    """A partner may discount, but never past 50%, however it is entered."""

    def _doc(self, percentage=0, amount=0, header_percentage=0, header_amount=0, qty=1):
        return Doc(
            customer="CUST-A",
            items=[
                Row(idx=1, item_code="WIDGET", uom="Nos", conversion_factor=1, qty=qty,
                    discount_percentage=percentage, discount_amount=amount)
            ],
            selling_price_list="x", additional_discount_percentage=header_percentage,
            discount_amount=header_amount, apply_discount_on="Grand Total",
        )

    def test_row_discounts_up_to_the_cap_are_allowed(self):
        for percentage, expected_rate in ((0, 50.0), (10, 45.0), (50, 25.0)):
            with self.subTest(percentage=percentage):
                doc = self._doc(percentage=percentage)
                PRICING.enforce_sales_order_pricing(doc)
                self.assertEqual(doc.items[0].rate, expected_rate)
                self.assertEqual(doc.items[0].discount_percentage, percentage)

    def test_a_row_discount_past_the_cap_is_refused(self):
        for percentage in (50.5, 51, 80, 100):
            with self.subTest(percentage=percentage), self.assertRaisesRegex(Exception, "more than the 50% allowed"):
                PRICING.enforce_sales_order_pricing(self._doc(percentage=percentage))

    def test_a_negative_discount_is_refused_so_it_cannot_be_a_markup(self):
        with self.assertRaisesRegex(Exception, "more than the 50% allowed"):
            PRICING.enforce_sales_order_pricing(self._doc(percentage=-5))

    def test_a_discount_typed_as_an_amount_counts_as_its_percentage(self):
        doc = self._doc(amount=20)  # 20 off a price of 50 = 40%
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual((doc.items[0].discount_percentage, doc.items[0].rate), (40.0, 30.0))
        with self.assertRaisesRegex(Exception, "more than the 50% allowed"):
            PRICING.enforce_sales_order_pricing(self._doc(amount=30))  # 60%

    def test_order_discount_is_capped_and_taken_off_the_net_total(self):
        doc = self._doc(header_percentage=50)
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.apply_discount_on, "Net Total")
        with self.assertRaisesRegex(Exception, "order discount can't be more than 50%"):
            PRICING.enforce_sales_order_pricing(self._doc(header_percentage=60))
        with self.assertRaisesRegex(Exception, "order discount can't be more than 50%"):
            PRICING.enforce_sales_order_pricing(self._doc(header_percentage=-1))

    def test_a_negative_order_discount_amount_is_refused(self):
        with self.assertRaisesRegex(Exception, "can't be negative"):
            PRICING.enforce_sales_order_pricing(self._doc(header_amount=-5))

    def test_the_client_cannot_lower_the_rate_instead_of_discounting(self):
        doc = self._doc()
        doc.items[0].rate = 1
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.items[0].rate, 50.0)

    # --- the combined effect, checked after ERPNext has calculated the totals ---------

    def _calculated(self, list_total_rows, net_total):
        return Doc(
            customer="CUST-A", docstatus=0, net_total=net_total,
            items=[Row(price_list_rate=rate, qty=qty) for rate, qty in list_total_rows],
        )

    def test_effective_discount_counts_row_and_order_discounts_together(self):
        # 200 at list, 60 net: row discounts and an order discount together took off 70%.
        self.assertAlmostEqual(PRICING.effective_discount_percentage(self._calculated([(100, 2)], 60)), 70.0)
        self.assertAlmostEqual(PRICING.effective_discount_percentage(self._calculated([(100, 2)], 200)), 0.0)
        self.assertEqual(PRICING.effective_discount_percentage(self._calculated([], 0)), 0.0)

    def test_two_discounts_that_compound_past_the_cap_are_refused(self):
        # 40% off the lines, then 30% off the order: 0.6 * 0.7 = 42% of list, a 58% discount.
        doc = self._calculated([(100, 2)], 200 * 0.6 * 0.7)
        with self.assertRaisesRegex(Exception, "total discount on this order is 58"):
            PRICING.enforce_discount_cap(doc)

    def test_a_total_discount_at_or_under_the_cap_is_fine(self):
        PRICING.enforce_discount_cap(self._calculated([(100, 2)], 100))        # exactly 50%
        PRICING.enforce_discount_cap(self._calculated([(100, 2)], 100.001))    # rounding
        PRICING.enforce_discount_cap(self._calculated([(100, 2)], 150))

    def test_a_big_order_level_amount_cannot_slip_past(self):
        with self.assertRaisesRegex(Exception, "more than the 50% allowed"):
            PRICING.enforce_discount_cap(self._calculated([(100, 2)], 20))     # 90% off

    def test_company_currency_totals_are_used_when_present(self):
        doc = Doc(customer="CUST-A", docstatus=0, net_total=1, base_net_total=100,
                  items=[Row(price_list_rate=1, base_price_list_rate=100, qty=2)])
        PRICING.enforce_discount_cap(doc)  # 100 of 200 in company currency = 50%, fine

    def test_staff_and_after_submit_edits_are_not_capped(self):
        STATE["partner"] = False
        PRICING.enforce_discount_cap(self._calculated([(100, 2)], 1))
        STATE["partner"] = True
        doc = self._calculated([(100, 2)], 1)
        doc._action = "update_after_submit"
        PRICING.enforce_discount_cap(doc)


class TestCommission(Base):
    def _doc(self, **extra):
        return Doc(
            customer="CUST-A",
            items=[Row(idx=1, item_code="WIDGET", uom="Nos", conversion_factor=1)],
            selling_price_list="x",
            **extra,
        )

    def test_partner_rate_is_used_when_the_customer_has_none(self):
        doc = self._doc()
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual((doc.sales_partner, doc.commission_rate), ("SP-A", 5.0))

    def test_customers_own_rate_wins_when_set(self):
        STATE["values"][("Customer", "CUST-A")]["default_commission_rate"] = 7
        doc = self._doc()
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.commission_rate, 7.0)

    def test_a_partner_cannot_choose_their_own_commission_or_partner(self):
        doc = self._doc(sales_partner="SP-B", commission_rate=100)
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual((doc.sales_partner, doc.commission_rate), ("SP-A", 5.0))

    def test_no_rate_anywhere_means_zero(self):
        STATE["values"][("Sales Partner", "SP-A")]["commission_rate"] = 0
        doc = self._doc(commission_rate=50)
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual(doc.commission_rate, 0.0)

    def test_staff_orders_are_left_alone(self):
        STATE["partner"] = False
        doc = self._doc(sales_partner="SP-B", commission_rate=3)
        PRICING.enforce_sales_order_pricing(doc)
        self.assertEqual((doc.sales_partner, doc.commission_rate), ("SP-B", 3))


class TestIsUnpriced(Base):
    def test_partner_is_not_offered_items_without_a_price(self):
        self.assertTrue(PRICING.is_unpriced({"item_code": "A"}, {}))
        self.assertTrue(PRICING.is_unpriced({"item_code": "A"}, {"price_list_rate": 0}))
        self.assertFalse(PRICING.is_unpriced({"item_code": "A"}, {"price_list_rate": 50}))

    def test_templates_are_exempt_because_their_variants_are_priced_individually(self):
        self.assertFalse(PRICING.is_unpriced({"item_code": "T", "has_variants": 1}, {}))

    def test_staff_see_every_item(self):
        STATE["partner"] = False
        self.assertFalse(PRICING.is_unpriced({"item_code": "A"}, {}))
        self.assertFalse(PRICING.is_unpriced({"item_code": "A"}, {"price_list_rate": 0}))


class TestElevation(Base):
    def test_runs_as_administrator_and_restores_the_user(self):
        with PRICING.as_system_user():
            self.assertEqual(FRAPPE.session.user, "Administrator")
        self.assertEqual(FRAPPE.session.user, "partner@example.com")

    def test_restores_the_user_when_the_call_raises(self):
        with self.assertRaises(RuntimeError):
            with PRICING.as_system_user():
                raise RuntimeError("boom")
        self.assertEqual(FRAPPE.session.user, "partner@example.com")


class TestPaymentFields(unittest.TestCase):
    def test_payment_and_credit_fields_are_neutralised(self):
        order = {"payments": [{"amount": 100}], "redeemed_customer_credit": 40,
                 "sales_order_settlement_state": "full", "customer": "C"}
        data = {"redeemed_customer_credit": 25, "payments": [{"amount": 1}]}
        PRICING.neutralise_payment_fields(order, data)
        for payload in (order, data):
            self.assertEqual(payload["payments"], [])
            self.assertEqual(payload["redeemed_customer_credit"], 0)
            self.assertEqual(payload["sales_order_settlement_state"], "none")
            self.assertEqual(payload["allow_no_payment_order_submit"], 1)
        self.assertEqual(order["customer"], "C")

    def test_missing_data_is_fine(self):
        order = {}
        PRICING.neutralise_payment_fields(order, None)
        self.assertEqual(order["payments"], [])


class TestItemRows(Base):
    META = _dict(
        stock_uom="Nos", custom_tfw_price=100, pos_on_sale_price=80, valuation_rate=12,
        standard_rate=20, default_bom="BOM-1", has_batch_no=0, has_serial_no=0, allow_negative_stock=0,
        item_name="Widget",
    )

    def _lookup(self):
        return FETCHERS.ItemLookupData(
            price_map={"WIDGET": {"Nos": _dict(price_list_rate=50, currency="GBP", uom="Nos")}},
            stock_map={"WIDGET": 5}, meta_map={"WIDGET": self.META},
            uom_map={}, barcode_map={}, batch_map={}, serial_map={},
            bom_map={"WIDGET": {"rate": 7, "source": "bom", "bom": "BOM-1"}},
        )

    def _row(self, partner):
        return FETCHERS.merge_item_row(
            {"item_code": "WIDGET", "uom": "Nos"}, self._lookup(), "GBP", 1.0, "GBP", partner_mode=partner
        )

    def test_staff_rows_are_unchanged(self):
        row = self._row(False)
        self.assertEqual(row["rate"], 80)  # on-sale beats TFW beats list
        self.assertEqual(row["valuation_rate"], 12)
        self.assertEqual(row["manufacturing_cost"], 7)

    def test_partner_rows_use_the_list_price_only(self):
        row = self._row(True)
        self.assertEqual((row["rate"], row["price_list_rate"]), (50, 50))
        self.assertFalse(row["is_on_sale"])

    def test_partner_rows_carry_no_cost_or_override_fields(self):
        row = self._row(True)
        for field in PRICING.HIDDEN_ITEM_FIELDS:
            self.assertNotIn(field, row)

    def test_partner_row_without_a_list_price_has_zero_rate(self):
        lookup = self._lookup()
        lookup.price_map.clear()
        row = FETCHERS.merge_item_row({"item_code": "WIDGET", "uom": "Nos"}, lookup, "GBP", 1.0, "GBP", partner_mode=True)
        self.assertEqual(row["price_list_rate"], 0)

    def test_item_detail_is_priced_and_scrubbed(self):
        detail = {"item_code": "WIDGET", "uom": "Nos", "rate": 80, "price_list_rate": 80,
                  "valuation_rate": 12, "last_purchase_rate": 9, "discount_percentage": 10}
        PRICING.apply_item_detail(detail, "CUST-A")
        self.assertEqual((detail["rate"], detail["price_list_rate"]), (50, 50))
        self.assertEqual(detail["selling_price_list"], "Trade GBP")
        self.assertEqual(detail["discount_percentage"], 0)
        self.assertNotIn("valuation_rate", detail)
        self.assertNotIn("last_purchase_rate", detail)

    def test_item_detail_for_another_partners_customer_is_refused(self):
        with self.assertRaises(FakePermissionError):
            PRICING.apply_item_detail({"item_code": "WIDGET"}, "CUST-B")


class TestAggregator(Base):
    def _aggregator(self, customer, **kw):
        profile = {"name": "POS", "currency": "GBP", "company": None, "selling_price_list": "Standard Selling"}
        return FETCHERS.ItemDetailAggregator(profile, price_list=kw.get("price_list"), customer=customer)

    def test_partner_price_list_cannot_be_chosen_by_the_client(self):
        self.assertEqual(self._aggregator("CUST-A", price_list="Standard Selling").price_list, "Trade GBP")

    def test_partner_needs_a_customer_in_scope(self):
        with self.assertRaises(FakePermissionError):
            self._aggregator("CUST-B")
        with self.assertRaisesRegex(Exception, "Select a customer first"):
            self._aggregator(None)

    def test_staff_keep_their_requested_price_list(self):
        STATE["partner"] = False
        self.assertEqual(self._aggregator("CUST-B", price_list="Standard Selling").price_list, "Standard Selling")


if __name__ == "__main__":
    unittest.main()
