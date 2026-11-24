"""Real-database tests for order_address.create_order_address (test_agile.localhost only).

Run from the bench ``sites`` dir with a connected site (never agile.localhost), e.g.

    ../env/bin/python <runner> posawesome.posawesome.api.test_order_address_db

The test site has no DHD Delivery Charge, so only the charge *fetch* (charge_pricing.get_charge,
plus the availability check) is stubbed, returning a charge whose ``order_type`` is the opaque
document id of a real Order Type named DHD (created here if the site has none, and rolled
back). The order-type resolution in ``_validated_dhd_charge`` runs for real. Everything else,
including permissions, naming and the Address/Dynamic Link rows, is real. Nothing is committed.
"""

import unittest
from unittest import mock

import frappe

from posawesome.posawesome.api import charge_pricing, order_address

GOOD = {
	"address_line1": "10 High Street",
	"city": "Peterborough",
	"postcode": "PE1 1AA",
	"country": "United Kingdom",
}


def _user(email, user_type, roles):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	user = frappe.get_doc(
		{"doctype": "User", "email": email, "first_name": "Zz", "user_type": user_type, "send_welcome_email": 0}
	)
	user.flags.ignore_permissions = True
	user.insert()
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email


class TestCreateOrderAddressDB(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		if frappe.local.site != "test_agile.localhost":
			raise unittest.SkipTest("only runs on test_agile.localhost")

	def setUp(self):
		frappe.set_user("Administrator")
		self.customer = frappe.db.get_value("Customer", {"disabled": 0}, "name")
		self.staff = _user("zz-oa-staff@example.com", "System User", ["Sales User"])
		self.web = _user("zz-oa-web@example.com", "Website User", [])
		self.dhd_type = frappe.db.get_value("Order Type", {"order_type_name": "DHD"})
		if not self.dhd_type:
			self.dhd_type = frappe.get_doc({"doctype": "Order Type", "order_type_name": "DHD"}).insert().name
		self.assertNotEqual(self.dhd_type, "DHD")  # generated id: the link value is not the name
		self.charge_order_type = self.dhd_type
		for patcher in (
			mock.patch.object(
				charge_pricing,
				"get_charge",
				side_effect=lambda name: frappe._dict(name=name, order_type=self.charge_order_type),
			),
			mock.patch.object(charge_pricing, "assert_available", return_value=None),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)

	def call(self, address=None, customer=None):
		return order_address.create_order_address(customer or self.customer, "ANY", address or GOOD)

	def test_unrelated_user_denied_before_any_lookup(self):
		# Seed an address first so a leak would be visible.
		frappe.set_user(self.staff)
		first = self.call()
		with mock.patch.object(order_address, "_existing_address") as lookup:
			for user in ("Guest", self.web):
				frappe.set_user(user)
				with self.subTest(user=user), self.assertRaises(frappe.PermissionError):
					self.call()
			lookup.assert_not_called()
		self.assertTrue(first["created"])

	def test_staff_create_dedupe_and_opaque_name(self):
		frappe.set_user(self.staff)
		first = self.call()
		self.assertTrue(first["created"])
		self.assertNotIn("High", first["name"])
		self.assertLessEqual(len(first["name"]), 140)
		doc = frappe.get_doc("Address", first["name"])
		self.assertEqual(doc.address_type, "Shipping")
		self.assertEqual([(l.link_doctype, l.link_name) for l in doc.links], [("Customer", self.customer)])

		again = self.call({**GOOD, "address_line1": "10, high street.", "postcode": "pe1  1aa"})
		self.assertEqual(again, {"name": first["name"], "created": False})
		self.assertTrue(self.call({**GOOD, "address_line1": "11 High Street"})["created"])

	def test_billing_address_is_not_reused(self):
		frappe.set_user(self.staff)
		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "Zz billing",
				"address_type": "Billing",
				"address_line1": GOOD["address_line1"],
				"city": "Peterborough",
				"pincode": "PE1 1AA",
				"country": "United Kingdom",
				"links": [{"link_doctype": "Customer", "link_name": self.customer}],
			}
		).insert(ignore_permissions=True)
		self.assertTrue(self.call()["created"])

	def test_charge_with_other_order_type_rejected(self):
		other = frappe.get_doc({"doctype": "Order Type", "order_type_name": "Zz not dhd"}).insert().name
		frappe.set_user(self.staff)
		self.charge_order_type = other
		with self.assertRaises(frappe.ValidationError):
			self.call()
		self.charge_order_type = "DHD"  # the literal string is not a valid Order Type id
		with self.assertRaises(frappe.ValidationError):
			self.call()

	def test_markup_rejected(self):
		frappe.set_user(self.staff)
		for payload in ("<img src=x onerror=alert(1)>", "<script>alert(1)</script>", '{"a": 1}'):
			with self.subTest(payload=payload), self.assertRaises(frappe.ValidationError):
				self.call({**GOOD, "address_line2": payload})

	def test_out_of_scope_partner_denied(self):
		with mock.patch("posawesome.posawesome.api.partner_gate.customer_scope_partners", return_value=["NO-SUCH-SP"]):
			with self.assertRaises(frappe.PermissionError):
				self.call()


if __name__ == "__main__":
	unittest.main()
