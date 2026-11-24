import importlib.util
import pathlib
import sys
import types
import unittest
import unittest.mock

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
        "customer_due_dates",
        "customer_due_dates.selling",
        "customer_due_dates.selling.pos_availability",
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

    def get_value(doctype, name, fieldname, as_dict=False):
        table = STATE["values"].get((doctype, name))
        if table is None:
            return None
        if isinstance(fieldname, (list, tuple)):
            if as_dict:
                return _dict({f: table.get(f) for f in fieldname})
            return tuple(table.get(f) for f in fieldname)
        return table.get(fieldname)

    frappe.throw = throw
    frappe.db = types.SimpleNamespace(
        get_value=get_value,
        has_column=lambda *a: True,
        exists=lambda doctype, name=None: (doctype, name) in STATE["values"],
    )
    frappe.bold = lambda text: text
    frappe.has_permission = lambda doctype, ptype=None, doc=None: True
    frappe.form_dict = _dict()

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

    cdd = types.ModuleType("customer_due_dates")
    cdd_selling = types.ModuleType("customer_due_dates.selling")
    availability = types.ModuleType("customer_due_dates.selling.pos_availability")
    availability.is_available = lambda value, partner_mode: (value or "TFW only") in (
        ["Agile only", "Both"] if partner_mode else ["TFW only", "Both"]
    )

    for name, mod in {
        "customer_due_dates": cdd,
        "customer_due_dates.selling": cdd_selling,
        "customer_due_dates.selling.pos_availability": availability,
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
    resolution = load("posawesome.posawesome.api.price_resolution", "price_resolution.py")
    api.price_resolution = resolution
    # The offer rules (get_applicable_delivery_charges) live in a doctype module that needs
    # a site; the fake offers whatever STATE["offered"] lists.
    for name in (
        "posawesome.posawesome.doctype",
        "posawesome.posawesome.doctype.delivery_charges",
    ):
        shell = types.ModuleType(name)
        shell.__path__ = []
        sys.modules[name] = shell
    dc_mod = types.ModuleType("posawesome.posawesome.doctype.delivery_charges.delivery_charges")
    dc_mod.get_applicable_delivery_charges = lambda company, profile, customer, *a, **k: [
        _dict(name=n) for n in STATE.get("offered", ())
    ]
    sys.modules["posawesome.posawesome.doctype.delivery_charges.delivery_charges"] = dc_mod
    fetchers = load("posawesome.posawesome.api.item_fetchers", "item_fetchers.py")
    api.item_fetchers = fetchers
    charges = load("posawesome.posawesome.api.charge_pricing", "charge_pricing.py")
    api.charge_pricing = charges
    pricing = load("posawesome.posawesome.api.partner_pricing", "partner_pricing.py")
    api.partner_pricing = pricing

    # Leave no stub behind for other test files.
    for name, mod in saved.items():
        if mod is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = mod
    charges.server_profile_context = lambda user=None: ("POS-A", "Co")
    return gate, fetchers, pricing, frappe, charges


GATE, FETCHERS, PRICING, FRAPPE, CHARGES = _install()
RESOLUTION = sys.modules.get('posawesome.posawesome.api.price_resolution') or PRICING.__dict__.get('price_resolution')


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
        self.partner_rows_flags = []

        def fake_fetch(price_list, currency, item_codes, customer, today, partner_rows=False):
            self.fetch_calls.append((price_list, currency, item_codes, customer))
            self.partner_rows_flags.append(partner_rows)
            return STATE["prices"]

        self._orig_fetch = FETCHERS._fetch_item_prices
        FETCHERS._fetch_item_prices = fake_fetch
        # Bind the module globals the code under test reads to this test's fakes.
        self._saved = {}
        for module in (GATE, PRICING, CHARGES, RESOLUTION):
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

    def test_pre_paid_advances_are_stripped_and_the_payment_type_is_left_alone(self):
        order = {"advance_paid": 90, "advances": [{"allocated_amount": 90}], "payment_type": "Proforma"}
        data = {"advance_paid": 5, "payment_type": "On Account"}
        PRICING.neutralise_payment_fields(order, data)
        for payload in (order, data):
            self.assertEqual(payload["advance_paid"], 0)
            self.assertNotIn("advances", payload)
        # decided by the submit against the POS Profile, not here
        self.assertEqual(order["payment_type"], "Proforma")
        self.assertEqual(data["payment_type"], "On Account")

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


class TestChargePricing(Base):
    """A delivery charge can fix the price list, give a fallback list and set availability."""

    def setUp(self):
        super().setUp()
        STATE["values"].update(
            {
                ("Delivery Charges", "DDP 40ft"): {
                    "order_type": "OT-DDP",
                    "price_list": "DDP 40ft",
                    "price_list_overrides_customer": 1,
                    "available_to": "Agile only",
                },
                ("Delivery Charges", "Free delivery"): {
                    "order_type": None,
                    "price_list": "Stockist",
                    "price_list_overrides_customer": 0,
                    "available_to": "Agile only",
                },
                ("Delivery Charges", "Standard Delivery"): {
                    "order_type": None,
                    "price_list": "Stockist",
                    "price_list_overrides_customer": 0,
                    "available_to": "TFW only",
                },
                ("Price List", "DDP 40ft"): {"enabled": 1, "selling": 1, "currency": "GBP"},
                ("Price List", "Stockist"): {"enabled": 1, "selling": 1, "currency": "GBP"},
                ("Price List", "Trade USD"): {"enabled": 1, "selling": 1, "currency": "USD"},
            }
        )
        STATE["values"][("Price List", "Trade GBP")]["fallback_price_list"] = "Stockist"
        STATE["offered"] = ["DDP 40ft", "Free delivery"]

    def test_container_charge_uses_only_its_own_list(self):
        self.assertEqual(PRICING.get_customer_price_list("CUST-A", "DDP 40ft"), "DDP 40ft")
        self.assertIsNone(CHARGES.fallback_for("DDP 40ft", "DDP 40ft"))
        self.assertIsNone(PRICING.resolve_pricing_context("CUST-A", "DDP 40ft").fallback)

    def test_standard_charge_keeps_the_customers_list_with_stockist_fallback(self):
        self.assertEqual(PRICING.get_customer_price_list("CUST-A", "Free delivery"), "Trade GBP")
        self.assertEqual(CHARGES.fallback_for("Trade GBP", "Free delivery"), "Stockist")
        self.assertEqual(PRICING.resolve_pricing_context("CUST-A", "Free delivery").fallback, "Stockist")

    def test_a_charge_that_is_not_offered_is_refused_before_any_price_is_read(self):
        # Disabled, wrong company/POS profile or restricted by the customer's address: the
        # offer rules (get_applicable_delivery_charges) leave it out.
        STATE["offered"] = ["Free delivery"]
        with self.assertRaises(FakePermissionError):
            PRICING.resolve_pricing_context("CUST-A", "DDP 40ft")
        with self.assertRaises(FakePermissionError):
            PRICING.apply_item_detail({"item_code": "WIDGET"}, "CUST-A", delivery_charge="DDP 40ft")
        self.assertEqual(self.fetch_calls, [])

    def test_an_unknown_charge_is_refused(self):
        with self.assertRaises(FakePermissionError):
            PRICING.resolve_pricing_context("CUST-A", "No such charge")

    def test_a_buying_only_or_disabled_fallback_is_never_used(self):
        for override in ({"selling": 0}, {"enabled": 0}):
            with self.subTest(override=override):
                STATE["values"][("Price List", "Stockist")] = {"enabled": 1, "selling": 1, "currency": "GBP", **override}
                self.assertIsNone(PRICING.resolve_pricing_context("CUST-A", "Free delivery").fallback)
                self.assertIsNone(PRICING.resolve_pricing_context("CUST-A").fallback)

    def test_a_locked_charge_whose_list_is_buying_only_is_an_error_not_a_fallback(self):
        STATE["values"][("Price List", "DDP 40ft")]["selling"] = 0
        with self.assertRaisesRegex(Exception, "not an enabled selling"):
            PRICING.resolve_pricing_context("CUST-A", "DDP 40ft")

    def test_rates_are_read_only_from_partner_visible_rows(self):
        PRICING.get_price_list_rate("WIDGET", "Trade GBP", "Nos", 1, "CUST-A")
        self.assertEqual(self.partner_rows_flags, [True])

    def test_gate_and_pricing_agree_on_the_lists(self):
        # The gate's list set is built from the same resolver: a locked charge adds only its
        # own list; a standard charge adds the customer's list and its fallback.
        self.assertEqual(RESOLUTION.resolve_lists("Trade GBP", None), ("Trade GBP", "Stockist"))
        self.assertEqual(
            RESOLUTION.resolve_lists("Trade GBP", {"price_list": "DDP 40ft", "price_list_overrides_customer": 1}),
            ("DDP 40ft", None),
        )
        self.assertEqual(RESOLUTION.resolve_lists(None, None), (None, None))

    def test_customer_without_a_list_uses_the_charges_list(self):
        self.assertEqual(PRICING.get_customer_price_list("CUST-NOLIST", "Free delivery"), "Stockist")

    def test_customer_without_a_list_and_no_charge_still_needs_one_set(self):
        with self.assertRaises(Exception):
            PRICING.get_customer_price_list("CUST-NOLIST")

    def test_fallback_never_crosses_currency(self):
        STATE["values"][("Price List", "Trade USD")]["fallback_price_list"] = "Stockist"
        self.assertIsNone(CHARGES.fallback_for("Trade USD"))

    def test_item_missing_from_the_customers_list_is_priced_from_the_fallback(self):
        calls = []

        def fake_rate(item_code, price_list, *a, **k):
            calls.append(price_list)
            return 20 if price_list == "Stockist" else None

        original = PRICING.get_price_list_rate
        PRICING.get_price_list_rate = fake_rate
        try:
            rate = PRICING.get_rate_with_fallback("WIDGET", "Trade GBP", "Stockist")
        finally:
            PRICING.get_price_list_rate = original
        self.assertEqual((rate, calls), (20, ["Trade GBP", "Stockist"]))

    def test_a_partner_cannot_use_a_tfw_only_charge(self):
        with self.assertRaises(FakePermissionError):
            CHARGES.assert_available("Standard Delivery")
        CHARGES.assert_available("Free delivery")

    def test_staff_cannot_use_an_agile_only_charge(self):
        STATE["partner"] = False
        with self.assertRaises(FakePermissionError):
            CHARGES.assert_available("DDP 40ft")
        CHARGES.assert_available("Standard Delivery")

    def test_charge_list_is_filtered_by_pos(self):
        rows = [{"name": "a", "available_to": "Agile only"}, {"name": "b", "available_to": "TFW only"},
                {"name": "c", "available_to": "Both"}, {"name": "d", "available_to": None}]
        self.assertEqual([r["name"] for r in CHARGES.filter_available(rows)], ["a", "c"])
        STATE["partner"] = False
        self.assertEqual([r["name"] for r in CHARGES.filter_available(rows)], ["b", "c", "d"])

    def test_charge_sets_the_order_type_on_the_order(self):
        doc = Doc(posa_delivery_charges="DDP 40ft", agiletfw_order_type=None, meta=types.SimpleNamespace(has_field=lambda f: True))
        CHARGES.apply_order_type(doc)
        self.assertEqual(doc.agiletfw_order_type, "OT-DDP")

    def test_charge_without_an_order_type_leaves_it_alone(self):
        doc = Doc(posa_delivery_charges="Free delivery", agiletfw_order_type="OT-KEEP", meta=types.SimpleNamespace(has_field=lambda f: True))
        CHARGES.apply_order_type(doc)
        self.assertEqual(doc.agiletfw_order_type, "OT-KEEP")

    def test_order_with_an_unavailable_charge_is_refused(self):
        doc = Doc(posa_delivery_charges="Standard Delivery", meta=types.SimpleNamespace(has_field=lambda f: True))
        with self.assertRaises(FakePermissionError):
            CHARGES.apply_order_type(doc)


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


class TestFixedEtaWeeksOnRows(Base):
    """AP-9: item-grid rows carry ``fixed_eta_weeks`` only on a fixed lead-time charge."""

    def setUp(self):
        super().setUp()
        STATE["values"].update(
            {
                ("Delivery Charges", "DDP 40ft"): {
                    "order_type": "OT-DDP", "price_list": "DDP 40ft",
                    "price_list_overrides_customer": 1, "available_to": "Agile only",
                },
                ("Delivery Charges", "DDP staff"): {
                    "order_type": "OT-DDP", "price_list": None,
                    "price_list_overrides_customer": 0, "available_to": "Both",
                },
                ("Delivery Charges", "Free delivery"): {
                    "order_type": "OT-PLAIN", "price_list": None,
                    "price_list_overrides_customer": 0, "available_to": "Agile only",
                },
                ("Delivery Charges", "No type"): {
                    "order_type": None, "price_list": None,
                    "price_list_overrides_customer": 0, "available_to": "Agile only",
                },
                ("Price List", "DDP 40ft"): {"enabled": 1, "selling": 1, "currency": "GBP"},
            }
        )
        STATE["offered"] = ["DDP 40ft", "DDP staff", "Free delivery", "No type"]
        self.lead_week_calls = []

        def lead_weeks_for_items(codes):
            self.lead_week_calls.append(list(codes))
            return {code: 12 if code == "SOFA" else 16 for code in codes}

        module = types.ModuleType("customer_due_dates.selling.fixed_eta")
        module.uses_fixed_eta = lambda order_type: order_type == "OT-DDP"
        module.lead_weeks_for_items = lead_weeks_for_items
        patcher = unittest.mock.patch.dict(sys.modules, {"customer_due_dates.selling.fixed_eta": module})
        patcher.start()
        self.addCleanup(patcher.stop)
        lookup = FETCHERS.ItemLookupData({}, {}, {}, {}, {}, {}, {}, {})
        self._saved_prepare = FETCHERS.ItemDetailAggregator._prepare_lookup
        self._saved_merge = FETCHERS.merge_item_row
        FETCHERS.ItemDetailAggregator._prepare_lookup = lambda agg, codes: lookup
        FETCHERS.merge_item_row = lambda item, *a, **k: {"item_code": item["item_code"], "price_list_rate": 1}
        self.addCleanup(setattr, FETCHERS.ItemDetailAggregator, "_prepare_lookup", self._saved_prepare)
        self.addCleanup(setattr, FETCHERS, "merge_item_row", self._saved_merge)

    ITEMS = [{"item_code": "SOFA"}, {"item_code": "TABLE"}, {"item_code": "SOFA"}, {"item_code": "TPL", "has_variants": 1}]

    def _rows(self, customer, charge):
        profile = {"name": "POS", "currency": "GBP", "company": None, "selling_price_list": "Standard Selling"}
        agg = FETCHERS.ItemDetailAggregator(profile, customer=customer, delivery_charge=charge)
        return agg.build_details(self.ITEMS)

    def test_fixed_charge_adds_weeks_in_one_batched_call(self):
        for partner, customer, charge in ((True, "CUST-A", "DDP 40ft"), (False, "CUST-B", "DDP staff")):
            with self.subTest(partner=partner):
                STATE["partner"] = partner
                self.lead_week_calls.clear()
                rows = self._rows(customer, charge)
                self.assertEqual([r["fixed_eta_weeks"] for r in rows], [12, 16, 12])
                self.assertEqual(len(self.lead_week_calls), 1, "one batched query for the page, no N+1")
                self.assertNotIn("TPL", self.lead_week_calls[0])

    def test_other_charges_leave_rows_unchanged(self):
        for charge in (None, "", "Free delivery", "No type"):
            with self.subTest(charge=charge):
                rows = self._rows("CUST-A", charge)
                self.assertTrue(rows)
                self.assertTrue(all("fixed_eta_weeks" not in r for r in rows))
        self.assertEqual(self.lead_week_calls, [])

    def test_staff_get_weeks_only_from_a_validated_charge(self):
        STATE["partner"] = False
        # "DDP 40ft" is Agile only: the raw charge has a fixed ETA but staff may not use it.
        self.assertTrue(all("fixed_eta_weeks" not in r for r in self._rows("CUST-B", "DDP 40ft")))
        # Not offered by the POS offer rules (company / profile / address charges): no weeks.
        STATE["offered"] = ["Free delivery"]
        self.assertTrue(all("fixed_eta_weeks" not in r for r in self._rows("CUST-B", "DDP staff")))
        self.assertEqual(self.lead_week_calls, [])

    def test_missing_lead_weeks_helper_leaves_ordinary_rows(self):
        # An older customer_due_dates that has the rule but not lead_weeks_for_items.
        module = types.ModuleType("customer_due_dates.selling.fixed_eta")
        module.uses_fixed_eta = lambda order_type: order_type == "OT-DDP"
        logged = []
        self.addCleanup(setattr, FETCHERS.frappe, "log_error", getattr(FETCHERS.frappe, "log_error", None))
        FETCHERS.frappe.log_error = lambda **kw: logged.append(kw)
        FETCHERS._LOGGED_MISSING_LEAD_WEEKS.clear()
        STATE["partner"] = True
        with unittest.mock.patch.dict(sys.modules, {"customer_due_dates.selling.fixed_eta": module}):
            first = self._rows("CUST-A", "DDP 40ft")
            second = self._rows("CUST-A", "DDP 40ft")
        self.assertEqual([r["item_code"] for r in first], ["SOFA", "TABLE", "SOFA"])
        self.assertTrue(all("fixed_eta_weeks" not in r for r in first + second))
        self.assertEqual(len(logged), 1, "logged once")

    def test_old_customer_due_dates_without_the_rule_adds_nothing(self):
        with unittest.mock.patch.dict(sys.modules, {"customer_due_dates.selling.fixed_eta": None}):
            rows = self._rows("CUST-A", "DDP 40ft")
        self.assertTrue(all("fixed_eta_weeks" not in r for r in rows))


if __name__ == "__main__":
    unittest.main()


class TestSanitisedItemDetailsInput(Base):
    """get_item_details runs as Administrator, so only validated inputs may reach it."""

    def test_client_rate_price_list_supplier_and_flags_are_dropped(self):
        item = {
            "item_code": "WIDGET", "qty": 2, "uom": "Nos", "warehouse": "WH",
            "rate": 1, "price_list_rate": 1, "price_list": "Standard Buying",
            "buying_price_list": "Standard Buying", "supplier": "SUP", "plc_conversion_rate": 9,
            "conversion_rate": 9, "ignore_pricing_rule": 0, "discount_percentage": 100,
            "customer": "CUST-B", "currency": "XXX",
        }
        clean, doc = PRICING.sanitise_item_details_input(item, "CUST-A", "Free delivery", "Trade GBP", "Co")
        for key in ("rate", "price_list_rate", "price_list", "buying_price_list", "supplier", "discount_percentage"):
            self.assertNotIn(key, clean)
        self.assertEqual(
            (clean["customer"], clean["selling_price_list"], clean["currency"], clean["conversion_rate"],
             clean["plc_conversion_rate"], clean["ignore_pricing_rule"], clean["item_code"], clean["qty"]),
            ("CUST-A", "Trade GBP", "GBP", 1, 1, 1, "WIDGET", 2),
        )
        self.assertEqual((doc["customer"], doc["selling_price_list"]), ("CUST-A", "Trade GBP"))
        self.assertNotIn("rate", doc)


class TestUomRate(Base):
    def test_partner_uom_rate_uses_the_customers_resolved_list_and_scales_the_stock_price(self):
        original = FRAPPE.db.get_value
        STATE["prices"] = _price_rows({"price_list_rate": 50, "uom": "Nos"})
        # conversion factor of Box = 6 via the fake UOM Conversion Detail lookup
        def get_value(doctype, name, fieldname=None, as_dict=False):
            if doctype == "UOM Conversion Detail":
                return 6 if name.get("uom") == "Box" else None
            return STATE["values"].get((doctype, name), {}).get(fieldname) if not isinstance(fieldname, (list, tuple)) else (
                _dict({f: STATE["values"].get((doctype, name), {}).get(f) for f in fieldname}) if as_dict else None)
        FRAPPE.db.get_value = get_value
        try:
            self.assertEqual(PRICING.get_uom_rate("WIDGET", "Box", "CUST-A"), 300)
            self.assertEqual(PRICING.get_uom_rate("WIDGET", "Nos", "CUST-A"), 50)
            self.assertIsNone(PRICING.get_uom_rate("WIDGET", "Pallet", "CUST-A"), "not a UOM of the item")
            with self.assertRaises(FakePermissionError):
                PRICING.get_uom_rate("WIDGET", "Nos", "CUST-B")
        finally:
            FRAPPE.db.get_value = original

