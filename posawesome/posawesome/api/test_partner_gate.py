import importlib.util
import json
import pathlib
import sys
import types
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parent / "partner_gate.py"

# Customer -> default_sales_partner, Sales Order -> customer
CUSTOMERS = {"CUST-A": "SP-A", "CUST-B": "SP-B", "CUST-NONE": None}
ORDERS = {"SO-A": "CUST-A", "SO-B": "CUST-B"}


class FakePermissionError(Exception):
    pass


def _load_gate(hooks=None):
    frappe = types.ModuleType("frappe")
    frappe.PermissionError = FakePermissionError
    frappe.session = types.SimpleNamespace(user="partner@example.com")
    frappe._ = lambda text: text
    frappe.local = types.SimpleNamespace()
    frappe.form_dict = {}

    def throw(msg, exc=Exception):
        raise exc(msg)

    def get_value(doctype, name, fieldname):
        table = {"Customer": CUSTOMERS, "Sales Order": ORDERS}[doctype]
        return table.get(name)

    frappe.throw = throw
    frappe.logged = []
    frappe.logger = lambda name: types.SimpleNamespace(warning=frappe.logged.append)
    frappe.db = types.SimpleNamespace(get_value=get_value)
    frappe.get_hooks = lambda key: (hooks or {}).get(key, [])
    frappe.get_attr = lambda path: (hooks or {}).get("_impl")[path]

    saved = sys.modules.get("frappe")
    sys.modules["frappe"] = frappe
    try:
        spec = importlib.util.spec_from_file_location("partner_gate_under_test", MODULE_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is not None:
            sys.modules["frappe"] = saved
        else:
            del sys.modules["frappe"]
    return module


GATE = _load_gate()
SCOPE = {"is_partner": True, "partners": ["SP-A"]}
NO_PARTNER_SCOPE = {"is_partner": True, "partners": []}
API = GATE.API


def call(method, form=None, scope=SCOPE, path=None, http="POST"):
    form = dict(form or {})
    GATE.check_request(scope, path or f"/api/method/{method}", http, form)


class TestScopeResolution(unittest.TestCase):
    def test_no_hook_means_nobody_is_a_partner(self):
        gate = _load_gate({})
        self.assertEqual(gate.get_scope("u"), {"is_partner": False, "partners": []})
        self.assertIsNone(gate.customer_scope_partners("u"))

    def test_hook_scope_is_read(self):
        impl = {"x.get_scope": lambda user: {"is_partner": True, "partners": ["SP-B", "SP-A", "SP-A"]}}
        gate = _load_gate({"posa_user_scope": ["x.get_scope"], "_impl": impl})
        self.assertEqual(gate.get_scope("u"), {"is_partner": True, "partners": ["SP-A", "SP-B"]})
        self.assertEqual(gate.customer_scope_partners("u"), ["SP-A", "SP-B"])

    def test_partner_without_partner_gets_match_nothing_sentinel(self):
        impl = {"x.get_scope": lambda user: {"is_partner": True, "partners": []}}
        gate = _load_gate({"posa_user_scope": ["x.get_scope"], "_impl": impl})
        self.assertEqual(gate.customer_scope_partners("u"), [gate.NO_PARTNER])

    def test_non_partner_hook_result_is_not_scoped(self):
        impl = {"x.get_scope": lambda user: {"is_partner": False, "partners": ["SP-A"]}}
        gate = _load_gate({"posa_user_scope": ["x.get_scope"], "_impl": impl})
        self.assertIsNone(gate.customer_scope_partners("u"))


class TestMethodAllowList(unittest.TestCase):
    def test_pos_allow_list_methods_pass(self):
        call(f"{API}utils.get_active_pos_profile")
        call(f"{API}items.get_items_count")
        call(f"{API}sales_orders.get_managed_sales_order_statuses")

    def test_offers_and_pricing_rules_are_not_available_to_partners(self):
        for method in (
            f"{API}offers.get_offers",
            f"{API}pricing_rules.get_active_pricing_rules",
            f"{API}pricing_rules.reconcile_line_prices",
        ):
            with self.subTest(method=method), self.assertRaises(FakePermissionError):
                call(method)

    def test_profile_locks_apply_to_documents_and_dicts(self):
        profile = {"customer": "WALK-IN", "posa_allow_user_to_edit_rate": 1}
        GATE.lock_pos_profile(profile)
        self.assertIsNone(profile["customer"])
        self.assertEqual(profile["posa_allow_user_to_edit_rate"], 0)
        self.assertEqual(profile["posa_force_price_from_customer_price_list"], 1)

        class Doc:
            def __init__(self):
                self.values = {}

            def set(self, key, value):
                self.values[key] = value

        doc = Doc()
        GATE.lock_pos_profile(doc)
        self.assertEqual(doc.values["posa_allow_return"], 0)

    def test_other_app_methods_are_denied_by_default(self):
        for method in (
            f"{API}payments.create_payment_request",
            f"{API}shifts.create_opening_voucher",
            f"{API}claims.raise_claim",
            f"{API}cash_movement.service.create_cash_deposit",
            f"{API}customers.create_customer",
            f"{API}customers.make_address",
            f"{API}sales_orders.pay_managed_sales_order_balance",
            f"{API}utilities.get_server_usage",
            f"{API}dashboard.get_dashboard_data",
            "customer_due_dates.api.anything",
            "erpnext.accounts.party.get_party_details",
            "helpdesk.api.anything",
            "not.a.real.method",
        ):
            with self.subTest(method=method), self.assertRaises(FakePermissionError):
                call(method)

    def test_real_module_path_of_a_reexport_is_not_allowed(self):
        with self.assertRaises(FakePermissionError):
            call(f"{API}item_processing.search.get_items")

    def test_framework_reads_allowed_writes_denied(self):
        call("frappe.client.get_list")
        call("frappe.desk.search.search_link")
        call("frappe.core.doctype.user.user.switch_theme")
        for method in (
            "frappe.client.insert",
            "frappe.client.set_value",
            "frappe.client.submit",
            "frappe.client.get_password",
            "frappe.desk.form.save.savedocs",
            "frappe.handler.upload_file",
            "frappe.handler.run_doc_method",
            "frappe.core.doctype.user.user.reset_password",
            "frappe.model.workflow.apply_workflow",
        ):
            with self.subTest(method=method), self.assertRaises(FakePermissionError):
                call(method)

    def test_path_suffix_cannot_smuggle_another_method(self):
        # Frappe runs only the part before the first "/".
        with self.assertRaises(FakePermissionError):
            call(f"{API}payments.create_payment_request/frappe.client.get_list")
        call("frappe.client.get_list/anything")

    def test_cmd_param_takes_priority_over_path(self):
        with self.assertRaises(FakePermissionError):
            call(
                "frappe.client.get_list",
                form={"cmd": f"{API}payments.create_payment_request"},
            )

    def test_a_partner_can_sign_in(self):
        # Frappe authenticates inside request setup, before before_request runs, so the
        # gate sees the partner's own login request with the user already set.
        call("login", {"usr": "partner@example.com", "pwd": "x"})
        call("login", path="/api/method/login")

    def test_shorthand_handler_calls(self):
        call("logout")
        with self.assertRaises(FakePermissionError):
            call("upload_file")
        with self.assertRaises(FakePermissionError):
            call("run_doc_method")


class TestDocumentRoutes(unittest.TestCase):
    def test_reads_allowed_writes_denied(self):
        for path in ("/api/resource/Customer", "/api/v2/document/Customer/CUST-A"):
            GATE.check_request(SCOPE, path, "GET", {})
            for verb in ("POST", "PUT", "DELETE", "PATCH"):
                with self.subTest(path=path, verb=verb), self.assertRaises(FakePermissionError):
                    GATE.check_request(SCOPE, path, verb, {})

    def test_non_api_pages_are_not_gated(self):
        GATE.check_request(SCOPE, "/app/posapp", "GET", {})
        GATE.check_request(SCOPE, "/assets/posawesome/x.js", "GET", {})


class TestCustomerArguments(unittest.TestCase):
    def test_required_customer(self):
        call(f"{API}customers.get_customer_info", {"customer": "CUST-A"})
        for form in ({"customer": "CUST-B"}, {"customer": "CUST-NONE"}, {"customer": ""}, {}):
            with self.subTest(form=form), self.assertRaises(FakePermissionError):
                call(f"{API}customers.get_customer_info", form)

    def test_balance_and_addresses_are_scoped(self):
        for method in (f"{API}customer.get_customer_balance", f"{API}customers.get_customer_addresses"):
            call(method, {"customer": "CUST-A"})
            with self.assertRaises(FakePermissionError):
                call(method, {"customer": "CUST-B"})

    def test_optional_customer(self):
        call(f"{API}items.get_items")
        call(f"{API}items.get_items", {"customer": ""})
        call(f"{API}items.get_items", {"customer": "CUST-A"})
        with self.assertRaises(FakePermissionError):
            call(f"{API}items.get_items", {"customer": "CUST-B"})

    def test_non_string_customer_is_denied(self):
        with self.assertRaises(FakePermissionError):
            call(f"{API}customers.get_customer_info", {"customer": ["CUST-A"]})

    def test_partner_with_no_partner_sees_nothing(self):
        with self.assertRaises(FakePermissionError):
            call(f"{API}customers.get_customer_info", {"customer": "CUST-A"}, scope=NO_PARTNER_SCOPE)


class TestOrderArguments(unittest.TestCase):
    def test_order_name_must_belong_to_partner(self):
        method = f"{API}sales_orders.get_managed_sales_order"
        call(method, {"sales_order": "SO-A"})
        for name in ("SO-B", "SO-MISSING", "", None):
            with self.subTest(name=name), self.assertRaises(FakePermissionError):
                call(method, {"sales_order": name})

    def test_other_order_readers(self):
        for fn in ("get_pos_order_summary", "get_managed_sales_order_new_item_details"):
            call(f"{API}sales_orders.{fn}", {"sales_order": "SO-A"})
            with self.assertRaises(FakePermissionError):
                call(f"{API}sales_orders.{fn}", {"sales_order": "SO-B"})


class TestOrderPayloads(unittest.TestCase):
    METHOD = f"{API}sales_orders.update_sales_order"

    def _send(self, payload, arg="data", method=None, wrap=json.dumps):
        call(method or self.METHOD, {arg: wrap(payload)})

    def test_new_order_for_own_customer(self):
        self._send({"customer": "CUST-A", "items": []})

    def test_new_order_for_other_or_missing_customer_denied(self):
        for payload in ({"customer": "CUST-B"}, {"customer": "CUST-NONE"}, {}, {"customer": ""}):
            with self.subTest(payload=payload), self.assertRaises(FakePermissionError):
                self._send(payload)

    def test_update_own_order(self):
        self._send({"name": "SO-A", "customer": "CUST-A"})
        self._send({"name": "SO-A"})

    def test_cannot_update_someone_elses_order(self):
        with self.assertRaises(FakePermissionError):
            self._send({"name": "SO-B"})
        with self.assertRaises(FakePermissionError):
            self._send({"name": "SO-B", "customer": "CUST-A"})

    def test_cannot_repoint_own_order_to_another_customer(self):
        with self.assertRaises(FakePermissionError):
            self._send({"name": "SO-A", "customer": "CUST-B"})

    def test_unknown_order_name_needs_an_in_scope_customer(self):
        self._send({"name": "SO-NEW", "customer": "CUST-A"})
        with self.assertRaises(FakePermissionError):
            self._send({"name": "SO-NEW"})

    def test_wrapped_and_dict_payloads(self):
        self._send({"data": {"customer": "CUST-A"}})
        self._send({"data": {"data": {"customer": "CUST-A"}}})
        self._send({"customer": "CUST-A"}, wrap=lambda p: p)
        with self.assertRaises(FakePermissionError):
            self._send({"data": {"customer": "CUST-B"}})
        with self.assertRaises(FakePermissionError):
            self._send({"data": json.dumps({"customer": "CUST-B"})}, wrap=lambda p: p)

    def test_malformed_payload_denied(self):
        for raw in ("not json", "[1, 2]", "42", None, ""):
            with self.subTest(raw=raw), self.assertRaises(FakePermissionError):
                call(self.METHOD, {"data": raw})

    def test_split_groups_cannot_name_other_customers(self):
        ok = {"customer": "CUST-A", "posa_split_groups": [{"group_id": "1", "customer": "CUST-A"}]}
        self._send(ok)
        bad = {"customer": "CUST-A", "posa_split_groups": {"1": {"group_id": "1", "customer": "CUST-B"}}}
        with self.assertRaises(FakePermissionError):
            self._send(bad)

    def test_order_argument_methods(self):
        for fn in (
            "submit_sales_order",
            "preview_quoted_delivery_window",
            "preview_split_group_delivery_windows",
        ):
            method = f"{API}sales_orders.{fn}"
            self._send({"customer": "CUST-A"}, arg="order", method=method)
            with self.assertRaises(FakePermissionError):
                self._send({"customer": "CUST-B"}, arg="order", method=method)

    def test_data_payload_methods(self):
        for fn in (
            "update_managed_sales_order",
            "update_managed_sales_order_items",
            "preview_managed_sales_order_items",
        ):
            method = f"{API}sales_orders.{fn}"
            self._send({"name": "SO-A"}, method=method)
            with self.assertRaises(FakePermissionError):
                self._send({"name": "SO-B"}, method=method)


class TestSelfUserRule(unittest.TestCase):
    METHOD = f"{API}shifts.check_opening_shift"

    def test_own_user_is_allowed(self):
        call(self.METHOD, {"user": "partner@example.com"})
        call(self.METHOD, {"user": "partner@example.com", "preferred_shift": "OPEN-1"})

    def test_another_users_shift_is_refused(self):
        for form in ({"user": "cashier@example.com"}, {"user": "Administrator"}, {"user": ""}, {}):
            with self.subTest(form=form), self.assertRaises(FakePermissionError):
                call(self.METHOD, form)


class TestPinCalls(unittest.TestCase):
    """The terminal lock: a partner may use their own PIN and nobody else's."""

    METHODS = ("get_cashier_pin_status", "save_cashier_pin", "verify_terminal_employee_pin")

    def test_own_pin_calls_are_allowed(self):
        for name in self.METHODS:
            with self.subTest(name=name):
                call(f"{API}employees.{name}", {"user": "partner@example.com", "pos_profile": "P"})

    def test_another_users_pin_is_refused(self):
        for name in self.METHODS:
            for user in ("cashier@example.com", "Administrator", "", None):
                with self.subTest(name=name, user=user), self.assertRaises(FakePermissionError):
                    call(f"{API}employees.{name}", {"user": user, "pos_profile": "P"})

    def test_listing_the_terminal_is_allowed_and_limited_in_the_function(self):
        call(f"{API}employees.get_terminal_employees", {"pos_profile": "P"})

    def test_the_rest_of_the_employee_module_stays_closed(self):
        for name in ("get_terminal_employees_all", "anything_else"):
            with self.assertRaises(FakePermissionError):
                call(f"{API}employees.{name}")


class TestBootPayload(unittest.TestCase):
    def _boot(self, scope):
        impl = {"x.get_scope": lambda _user: scope}
        gate = _load_gate({"posa_user_scope": ["x.get_scope"], "_impl": impl})
        boot = types.SimpleNamespace()
        gate.extend_boot(boot)
        return gate, boot

    def test_partner_gets_the_allow_list_the_server_enforces(self):
        gate, boot = self._boot(SCOPE)
        mode = boot.posa_partner_mode
        self.assertEqual(mode["partners"], ["SP-A"])
        self.assertEqual(mode["allowed_methods"], sorted(gate.POS_METHODS))
        self.assertIn(f"{API}items.get_items", mode["allowed_methods"])
        self.assertNotIn(f"{API}payments.create_payment_request", mode["allowed_methods"])
        self.assertIn(f"{API}items.get_items", mode["customer_methods"])
        self.assertIn(f"{API}items.get_items_details", mode["customer_methods"])
        self.assertIn(f"{API}customers.get_customer_info", mode["customer_methods"])
        self.assertNotIn(f"{API}utils.get_active_pos_profile", mode["customer_methods"])
        self.assertTrue(set(mode["customer_methods"]) <= set(mode["allowed_methods"]))
        self.assertEqual(mode["framework_denied"], list(gate.FRAMEWORK_DENIED))
        self.assertEqual(mode["framework_allowed"], list(gate.FRAMEWORK_ALLOWED))
        self.assertEqual(mode["shorthand_allowed"], list(gate.SHORTHAND_ALLOWED))

    def test_non_partner_gets_nothing(self):
        _gate, boot = self._boot({"is_partner": False, "partners": []})
        self.assertFalse(hasattr(boot, "posa_partner_mode"))


class TestEnforceEntryPoint(unittest.TestCase):
    def _gate(self, user, scope):
        impl = {"x.get_scope": lambda _user: scope}
        gate = _load_gate({"posa_user_scope": ["x.get_scope"], "_impl": impl})
        gate.frappe.session.user = user
        gate.frappe.local.request = types.SimpleNamespace(
            path=f"/api/method/{API}payments.create_payment_request", method="POST"
        )
        return gate

    def test_guest_and_non_partner_pass(self):
        self._gate("Guest", SCOPE).enforce()
        self._gate("cashier@example.com", {"is_partner": False, "partners": []}).enforce()

    def test_partner_is_gated(self):
        with self.assertRaises(FakePermissionError):
            self._gate("partner@example.com", SCOPE).enforce()

    def test_denials_are_logged_with_the_method(self):
        gate = self._gate("partner@example.com", SCOPE)
        with self.assertRaises(FakePermissionError):
            gate.enforce()
        self.assertEqual(len(gate.frappe.logged), 1)
        self.assertIn("partner@example.com", gate.frappe.logged[0])
        self.assertIn("payments.create_payment_request", gate.frappe.logged[0])


class TestHookRegistration(unittest.TestCase):
    """API key / OAuth requests only have a user after Frappe authenticates them, which is
    after before_request, so the gate must also be an auth hook or token auth skips it."""

    def _hooks_source(self):
        return (MODULE_PATH.parents[2] / "hooks.py").read_text()

    def test_gate_runs_for_cookie_and_token_requests(self):
        import re

        source = self._hooks_source()
        for hook in ("before_request", "auth_hooks"):
            match = re.search(rf"^{hook}\s*=\s*\[(.*?)\]", source, re.M | re.S)
            self.assertIsNotNone(match, hook)
            self.assertIn("posawesome.posawesome.api.partner_gate.enforce", match.group(1), hook)

    def test_partner_pricing_runs_on_every_sales_order_validate(self):
        import re

        source = self._hooks_source()
        match = re.search(r'"Sales Order":\s*\{(.*?)\}', source, re.S)
        self.assertIsNotNone(match)
        self.assertIn(
            '"before_validate": "posawesome.posawesome.api.partner_pricing.enforce_sales_order_pricing"',
            match.group(1),
        )


if __name__ == "__main__":
    unittest.main()
