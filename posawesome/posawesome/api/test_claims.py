"""Integration tests for the POSAwesome Customer Claims endpoints.

These check the POSAwesome seam only — the raise/list/detail wrappers and their
permission boundary. Every claim rule and workflow transition is owned and tested
by ``customer_due_dates.customer_claims``.

Run on the test site:

    bench --site test_agile.localhost run-tests \
      --module posawesome.posawesome.api.test_claims --skip-before-tests
"""

import frappe
from frappe.tests.classes import IntegrationTestCase
from frappe.utils import now_datetime

# 1x1 transparent PNG.
_PNG_BASE64 = (
	"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

from customer_due_dates.customer_claims import workspace as claim_workspace
from customer_due_dates.customer_claims.setup import setup as setup_claims
from posawesome.posawesome.api import claims


class TestPosawesomeClaims(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.addCleanup(frappe.set_user, "Administrator")
		self.addCleanup(frappe.db.rollback)
		setup_claims()

		self.token = frappe.generate_hash(length=8)
		self.approver = self.make_user("pos-claim-approver", ["Claim User", "Claim Approver", "Sales User"])
		self.outsider = self.make_user("pos-claim-outsider", [])

		self.claim_type = frappe.get_doc(
			dict(doctype="Customer Claim Type", claim_type_name=f"_POS Claims {self.token}")
		).insert().name
		self.customer = self.raw("Customer", customer_name="_POS Claim Customer").name
		self.company = self.raw(
			"Company", company_name="_POS Claim Company", default_currency="GBP"
		).name
		self.item = self.raw(
			"Item", item_code=f"_POS Claim Item {self.token}", item_name="_POS Claim Item", stock_uom="Nos"
		).name
		self.order = self._sales_order(rfs_order=1)
		self.line = self._sales_order_line(self.order)
		# A non-RFS order and one claim on it — POSAwesome must never surface these.
		self.other_order = self._sales_order(rfs_order=0)
		self.other_line = self._sales_order_line(self.other_order)

	def _sales_order(self, rfs_order=1):
		return self.raw(
			"Sales Order",
			customer=self.customer,
			company=self.company,
			currency="GBP",
			docstatus=1,
			rfs_order=rfs_order,
		)

	def _sales_order_line(self, order):
		return self.raw(
			"Sales Order Item",
			parent=order.name,
			parenttype="Sales Order",
			parentfield="items",
			idx=1,
			item_code=self.item,
			item_name="_POS Claim Item",
			qty=3,
			uom="Nos",
		)

	def raw(self, doctype, **values):
		doc = frappe.get_doc(
			dict(
				doctype=doctype,
				name=f"_POS-Claims-{frappe.generate_hash(length=10)}",
				owner="Administrator",
				modified_by="Administrator",
				creation=now_datetime(),
				modified=now_datetime(),
				**values,
			)
		)
		doc.db_insert()
		return doc

	def make_user(self, prefix, roles):
		user = frappe.get_doc(
			dict(
				doctype="User",
				email=f"{prefix}-{self.token}@example.com",
				first_name="_POS Claims",
				enabled=1,
				send_welcome_email=0,
				user_type="System User",
				roles=[dict(role=r) for r in roles],
			)
		)
		user.insert(ignore_permissions=True)
		return user.name

	def _payload(self, order, line):
		return dict(
			sales_order=order.name,
			claim_type=self.claim_type,
			description="Arrived damaged",
			preferred_outcome="Replace",
			items=[dict(sales_order_item=line.name, qty=2, fault_details="Cracked casing")],
		)

	def _raise(self):
		return claims.raise_claim(self._payload(self.order, self.line))

	def test_context_lists_order_lines_and_claim_types(self):
		frappe.set_user(self.approver)
		context = claims.get_sales_order_claim_context(self.order.name)
		self.assertEqual(context["customer"], self.customer)
		self.assertEqual([row["sales_order_item"] for row in context["items"]], [self.line.name])
		self.assertIn(self.claim_type, [row["name"] for row in context["claim_types"]])
		self.assertIn("Replace", context["preferred_outcomes"])
		self.assertEqual(context["existing_claims"], [])

	def test_raise_then_context_reports_the_existing_claim(self):
		frappe.set_user(self.approver)
		result = self._raise()
		self.assertTrue(result["name"])

		context = claims.get_sales_order_claim_context(self.order.name)
		self.assertEqual(len(context["existing_claims"]), 1)
		existing = context["existing_claims"][0]
		self.assertEqual(existing["name"], result["name"])
		self.assertEqual(
			[row["sales_order_item"] for row in existing["items"]], [self.line.name]
		)

	def test_claim_summary_counts_claims_on_the_order(self):
		frappe.set_user(self.approver)
		self.assertEqual(claims.get_sales_order_claim_summary(self.order.name), {"count": 0})
		self._raise()
		self.assertEqual(claims.get_sales_order_claim_summary(self.order.name), {"count": 1})

	def test_list_claims_filters_by_sales_order(self):
		another_rfs = self._sales_order(rfs_order=1)
		frappe.set_user(self.approver)
		raised = self._raise()

		on_order = claims.list_claims(sales_order=self.order.name)
		self.assertEqual([row.name for row in on_order["claims"]], [raised["name"]])

		none_here = claims.list_claims(sales_order=another_rfs.name)
		self.assertEqual(none_here["claims"], [])

	def test_pos_claims_are_limited_to_rfs_orders(self):
		frappe.set_user(self.approver)
		rfs_claim = self._raise()
		# Seed a claim on the non-RFS order straight through the shared workspace,
		# bypassing the POSAwesome RFS guard, to prove the read side filters it out.
		non_rfs_claim = claim_workspace.create_claim(self._payload(self.other_order, self.other_line))

		listed = claims.list_claims()
		names = [row.name for row in listed["claims"]]
		self.assertIn(rfs_claim["name"], names)
		self.assertNotIn(non_rfs_claim["name"], names)
		self.assertEqual(listed["counts"]["open"], 1)

		self.assertEqual(
			claims.get_sales_order_claim_summary(self.other_order.name), {"count": 0}
		)
		with self.assertRaises(frappe.PermissionError):
			claims.get_sales_order_claim_context(self.other_order.name)
		with self.assertRaises(frappe.PermissionError):
			claims.get_claim(non_rfs_claim["name"])
		with self.assertRaises(frappe.PermissionError):
			claims.raise_claim(self._payload(self.other_order, self.other_line))

	def test_list_and_detail_round_trip(self):
		frappe.set_user(self.approver)
		result = self._raise()

		overview = claims.list_claims(search=self.order.name)
		self.assertIn(result["name"], [row.name for row in overview["claims"]])
		self.assertEqual(overview["counts"]["open"], 1)

		detail = claims.get_claim(result["name"])
		self.assertEqual(detail["claim"]["sales_order"], self.order.name)
		self.assertEqual(detail["claim"]["preferred_outcome"], "Replace")
		self.assertEqual(
			[row["sales_order_item"] for row in detail["claim"]["items"]], [self.line.name]
		)

	def test_outsider_cannot_read_or_raise(self):
		frappe.set_user(self.outsider)
		with self.assertRaises(frappe.PermissionError):
			claims.get_sales_order_claim_context(self.order.name)
		with self.assertRaises(frappe.PermissionError):
			self._raise()
		with self.assertRaises(frappe.PermissionError):
			claims.list_claims()
		with self.assertRaises(frappe.PermissionError):
			claims.upload_claim_evidence("x.png", _PNG_BASE64)

	def test_evidence_upload_and_required_evidence_claim(self):
		frappe.db.set_value("Customer Claim Type", self.claim_type, "evidence_required", 1)

		frappe.set_user(self.approver)
		with self.assertRaises(frappe.ValidationError):
			claims.upload_claim_evidence("notes.txt", _PNG_BASE64)

		uploaded = claims.upload_claim_evidence("damage.png", _PNG_BASE64)
		self.assertTrue(uploaded["file_url"])
		self.assertTrue(frappe.db.get_value("File", {"file_url": uploaded["file_url"]}, "is_private"))

		result = claims.raise_claim(
			dict(
				sales_order=self.order.name,
				claim_type=self.claim_type,
				description="Cracked on arrival",
				preferred_outcome="Replace",
				evidence=uploaded["file_url"],
				items=[dict(sales_order_item=self.line.name, qty=1)],
			)
		)
		self.assertEqual(
			frappe.db.get_value("Customer Claim", result["name"], "evidence"), uploaded["file_url"]
		)
