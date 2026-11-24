import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate

from posawesome.posawesome.api import partner_commission

ROLE = "POS Sales Partner"


def _user(email):
    if frappe.db.exists("User", email):
        return email
    user = frappe.get_doc(
        {"doctype": "User", "email": email, "first_name": "T", "send_welcome_email": 0, "enabled": 1}
    ).insert(ignore_permissions=True)
    user.add_roles(ROLE)
    return user.name


def _partner(name, user):
    if not frappe.db.exists("Sales Partner", name):
        frappe.get_doc(
            {
                "doctype": "Sales Partner",
                "partner_name": name,
                "commission_rate": 10,
                "territory": frappe.db.get_value("Territory", {"is_group": 0}, "name")
                or "All Territories",
                "portal_users": [{"user": user}],
            }
        ).insert(ignore_permissions=True)
    return name


class TestPartnerCommission(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not frappe.db.exists("Role", ROLE):
            frappe.get_doc({"doctype": "Role", "role_name": ROLE}).insert(ignore_permissions=True)
        suffix = frappe.generate_hash(length=5)
        cls.user_a = _user(f"pc-a-{suffix}@example.com")
        cls.user_b = _user(f"pc-b-{suffix}@example.com")
        cls.partner_a = _partner(f"PC Partner A {suffix}", cls.user_a)
        cls.partner_b = _partner(f"PC Partner B {suffix}", cls.user_b)
        cls.orders = {}
        for key, partner, delivered, net in (
            ("a1", cls.partner_a, 100, 1000),
            ("a2", cls.partner_a, 0, 500),
            ("b1", cls.partner_b, 100, 2000),
        ):
            cls.orders[key] = cls._order(partner, delivered, net)

    @classmethod
    def _order(cls, partner, delivered, net):
        name = frappe.generate_hash(length=10)
        frappe.db.sql(
            """insert into `tabSales Order`
            (name, creation, modified, owner, modified_by, docstatus, status, transaction_date,
             customer, customer_name, sales_partner, commission_rate, amount_eligible_for_commission,
             total_commission, per_delivered)
            values (%s, now(), now(), 'Administrator', 'Administrator', 1, 'To Deliver', %s,
             'PC-CUST', 'PC Customer', %s, 10, %s, %s, %s)""",
            (name, nowdate(), partner, net, net / 10, delivered),
        )
        return name

    def _as(self, user, **kwargs):
        frappe.set_user(user)
        try:
            return partner_commission.get_partner_commission(**kwargs)
        finally:
            frappe.set_user("Administrator")

    def test_partner_sees_only_own_orders_with_totals(self):
        result = self._as(self.user_a)
        names = {r["name"] for r in result["rows"]}
        self.assertEqual(names, {self.orders["a1"], self.orders["a2"]})
        self.assertEqual(result["totals"]["orders"], 2)
        self.assertEqual(result["totals"]["net_value"], 1500)
        self.assertEqual(result["totals"]["commission"], 150)

    def test_delivered_only_narrows_rows_and_totals(self):
        result = self._as(self.user_a, delivered_only=1)
        self.assertEqual([r["name"] for r in result["rows"]], [self.orders["a1"]])
        self.assertEqual(result["totals"]["commission"], 100)

    def test_rows_and_totals_reconcile(self):
        result = self._as(self.user_a)
        self.assertEqual(sum(r["commission"] for r in result["rows"]), result["totals"]["commission"])
        for row in result["rows"]:
            self.assertEqual(round(row["net_value"] * row["commission_rate"] / 100, 2), row["commission"])

    def test_non_partner_is_refused(self):
        with self.assertRaises(frappe.PermissionError):
            partner_commission.get_partner_commission()
        frappe.set_user("Administrator")

    def test_paging_keeps_whole_set_totals(self):
        result = self._as(self.user_a, limit=1)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(result["totals"]["orders"], 2)
