"""Integration tests for the POSAwesome Customer Claims endpoints.

These check the POSAwesome seam only — the raise/list/detail wrappers and their
permission boundary. Every claim rule and workflow transition is owned and tested
by ``customer_due_dates.customer_claims``.

Run on the test site:

    bench --site test_agile.localhost run-tests \
      --module posawesome.posawesome.api.test_claims --skip-before-tests
"""

import base64
from unittest.mock import patch

import frappe
from frappe.model.workflow import apply_workflow
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
		self.cashier = self.make_user("pos-claim-cashier", ["Claim User", "Sales User"])
		self.pos_profile_name = f"_POS Claims Profile {self.token}"
		self._register_terminal_user(self.pos_profile_name, self.cashier)

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

	def _register_terminal_user(self, profile_name, user):
		"""A raw 'POS Profile User' child row -- enough for _get_terminal_users'
		plain frappe.get_all(filters={"parent": profile_name}) query to find it,
		with no need for a real, fully-valid POS Profile parent document."""
		self.raw(
			"POS Profile User",
			parent=profile_name,
			parenttype="POS Profile",
			parentfield="applicable_for_users",
			idx=1,
			user=user,
		)

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

	def _payload(self, order, line, **overrides):
		values = dict(
			sales_order=order.name,
			claim_type=self.claim_type,
			description="Arrived damaged",
			preferred_outcome="Replace",
			items=[dict(sales_order_item=line.name, qty=2, fault_details="Cracked casing")],
		)
		values.update(overrides)
		return values

	def _raise(self, **overrides):
		return claims.raise_claim(self._payload(self.order, self.line, **overrides))

	def test_context_lists_order_lines_and_claim_types(self):
		frappe.set_user(self.approver)
		context = claims.get_sales_order_claim_context(self.order.name)
		self.assertEqual(context["customer"], self.customer)
		self.assertEqual([row["sales_order_item"] for row in context["items"]], [self.line.name])
		self.assertIn(self.claim_type, [row["name"] for row in context["claim_types"]])
		self.assertIn("Replace", context["preferred_outcomes"])
		self.assertEqual(context["existing_claims"], [])

	def test_raise_claim_defaults_to_the_session_user_with_no_cashier_selected(self):
		"""No pos_profile/assigned_to in the payload -- e.g. an older client, or
		before a cashier is picked -- keeps today's behaviour: both fields fall
		back to whoever the terminal is actually logged into ERP as."""
		frappe.set_user(self.approver)
		result = self._raise()
		doc = frappe.get_doc("Customer Claim", result["name"])
		self.assertEqual(doc.assigned_to, self.approver)
		self.assertEqual(doc.owner, self.approver)

	def test_raise_claim_attributes_to_the_selected_pos_cashier(self):
		"""The shared terminal login (self.approver) raises the request, but a
		different, registered cashier (self.cashier) is selected on the till --
		both the claim's own "Claim Owner" (assigned_to) and Frappe's own
		"Raised by" (owner) must reflect the cashier, not the terminal login.
		self.cashier only holds Claim User (not Claim Approver), so this also
		covers that the claim needs approval rather than auto-approving --
		see test_raise_claim_by_a_non_approver_cashier_does_not_auto_approve
		for that as an explicit, dedicated regression."""
		frappe.set_user(self.approver)
		result = self._raise(assigned_to=self.cashier, pos_profile=self.pos_profile_name)
		doc = frappe.get_doc("Customer Claim", result["name"])
		self.assertEqual(doc.assigned_to, self.cashier)
		self.assertEqual(doc.owner, self.cashier)
		self.assertEqual(doc.workflow_state, "Pending Approval")

	def test_raise_claim_by_a_non_approver_cashier_does_not_auto_approve(self):
		"""Real bug (claim CC-03650): the shared terminal is logged into ERP as
		a Claim Approver (self.approver), but the cashier actually raising the
		claim (self.cashier) only holds Claim User -- the claim must go
		through Pending Approval like any other Claim User's claim, not
		auto-approve itself just because of who the terminal happens to be
		logged in as. `result["workflow_state"]` is what raise_claim itself
		reports back to the POS UI, so this checks that directly too, not just
		the record afterwards."""
		frappe.set_user(self.approver)
		result = self._raise(assigned_to=self.cashier, pos_profile=self.pos_profile_name)
		self.assertEqual(result["workflow_state"], "Pending Approval")
		doc = frappe.get_doc("Customer Claim", result["name"])
		self.assertEqual(doc.workflow_state, "Pending Approval")
		self.assertFalse(doc.approved_by)

	def test_raise_claim_by_an_approver_cashier_still_auto_approves(self):
		"""The flip side of the CC-03650 fix: when the selected cashier
		genuinely does hold Claim Approver, auto-approval must still happen --
		this isn't a "POS never auto-approves" rule, it's "auto-approval
		follows the real actor's role", and the transition itself still runs
		under the terminal's own (real, permission-checked) session, which
		here is also a Claim Approver so nothing about executing the
		transition changes."""
		approver_cashier = self.make_user(
			"pos-claim-approver-cashier", ["Claim User", "Claim Approver", "Sales User"]
		)
		self._register_terminal_user(self.pos_profile_name, approver_cashier)
		frappe.set_user(self.approver)
		result = self._raise(assigned_to=approver_cashier, pos_profile=self.pos_profile_name)
		self.assertEqual(result["workflow_state"], "Approved")
		doc = frappe.get_doc("Customer Claim", result["name"])
		self.assertEqual(doc.workflow_state, "Approved")
		self.assertEqual(doc.assigned_to, approver_cashier)
		self.assertEqual(doc.owner, approver_cashier)

	def test_raise_claim_ignores_a_cashier_not_registered_to_the_profile(self):
		"""A requested cashier not actually on that POS Profile's roster (stale
		client state, wrong profile, or a forged payload) must not be trusted --
		falls back to the real session user instead of attributing the claim to
		an arbitrary, unrelated one."""
		frappe.set_user(self.approver)
		unregistered = self.make_user("pos-claim-unregistered", ["Claim User"])
		result = self._raise(assigned_to=unregistered, pos_profile=self.pos_profile_name)
		doc = frappe.get_doc("Customer Claim", result["name"])
		self.assertEqual(doc.assigned_to, self.approver)
		self.assertEqual(doc.owner, self.approver)

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

	def test_summary_counts_are_not_scoped_to_a_single_sales_order(self):
		"""The top summary tiles are the full, business-wide totals -- arriving
		pre-filtered to one order (POS's "Show claims" shortcut from Sales
		Order Management) must not shrink them down to just that order's own
		claim(s), or they'd almost always misleadingly read 0 or 1. The list
		itself still narrows to the one order; only the counts don't."""
		another_rfs = self._sales_order(rfs_order=1)
		another_line = self._sales_order_line(another_rfs)
		frappe.set_user(self.approver)
		self._raise()
		claims.raise_claim(self._payload(another_rfs, another_line))

		scoped = claims.list_claims(sales_order=self.order.name)
		self.assertEqual(len(scoped["claims"]), 1)
		self.assertEqual(scoped["counts"]["open"], 2)

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
		# Different bytes: identical uploads share one URL.
		second = claims.upload_claim_evidence("label.png", base64.b64encode(b"second photo").decode())

		result = claims.raise_claim(
			dict(
				sales_order=self.order.name,
				claim_type=self.claim_type,
				description="Cracked on arrival",
				preferred_outcome="Replace",
				evidence=[uploaded["file_url"], second["file_url"]],
				items=[dict(sales_order_item=self.line.name, qty=1)],
			)
		)
		detail = claims.get_claim(result["name"])
		self.assertEqual(
			[row["file"] for row in detail["claim"]["evidence_files"]],
			[uploaded["file_url"], second["file_url"]],
		)

	def test_video_evidence_upload_and_per_kind_size_limits(self):
		frappe.set_user(self.approver)
		video = claims.upload_claim_evidence("damage.MOV", base64.b64encode(b"video bytes").decode())
		self.assertTrue(video["file_url"].lower().endswith(".mov"))
		self.assertTrue(frappe.db.get_value("File", {"file_url": video["file_url"]}, "is_private"))

		context = claims.get_sales_order_claim_context(self.order.name)
		self.assertLessEqual(context["evidence_max_bytes"]["photo"], context["evidence_max_bytes"]["video"])

		# A video may be larger than a photo is allowed to be.
		with patch.object(claims, "_evidence_limits", return_value={"photo": 4, "video": 8}):
			claims.upload_claim_evidence("clip.mp4", base64.b64encode(b"sixbyt").decode())
			with self.assertRaises(frappe.ValidationError):
				claims.upload_claim_evidence("photo.jpg", base64.b64encode(b"sixbyt").decode())
			with self.assertRaises(frappe.ValidationError):
				claims.upload_claim_evidence("clip.mp4", base64.b64encode(b"ninebytes").decode())

	def _decision_payload(self, claim_name):
		claim = frappe.get_doc("Customer Claim", claim_name)
		return dict(
			claim=claim_name,
			outcome="Replace",
			reasoning="Confirmed faulty on inspection.",
			items=[
				dict(
					claim_item=claim.items[0].name,
					qty=1,
					replacement_item=self.item,
					replacement_qty=1,
				)
			],
		)

	def test_propose_decision_from_pos_always_needs_approval(self):
		"""Real bug (claim CC-03651): a decision proposed through POS must
		never auto-approve off the shared terminal's own Frappe session role
		(self.approver here) -- there's no reliable way yet to know which
		specific person at the till actually proposed it (unlike claims,
		Decision has no cashier-attribution field -- see [[customer-claims-
		overhaul]]'s "skip decisions for now" note), so it always needs a real
		Desk user's own review before it takes effect."""
		frappe.set_user(self.approver)
		raised = self._raise()
		decision = claims.propose_decision(self._decision_payload(raised["name"]))
		self.assertEqual(decision["workflow_state"], "Pending Approval")

		detail = claims.get_claim(raised["name"])
		self.assertEqual([d["name"] for d in detail["decisions"]], [decision["name"]])
		# Not yet advanced -- only an *approved* decision moves claim progress.
		self.assertEqual(detail["claim"]["progress"], "Under Review")

		doc = frappe.get_doc("Customer Claim Decision", decision["name"])
		approved = apply_workflow(doc, "Approve")
		self.assertEqual(approved.workflow_state, "Approved")
		detail = claims.get_claim(raised["name"])
		self.assertEqual(detail["claim"]["progress"], "In Progress")
		self.assertIn("Awaiting Customer", detail["progress_actions"])

	def test_decision_endpoints_refuse_non_rfs_claims(self):
		frappe.set_user(self.approver)
		non_rfs = claim_workspace.create_claim(self._payload(self.other_order, self.other_line))
		with self.assertRaises(frappe.PermissionError):
			claims.propose_decision(self._decision_payload(non_rfs["name"]))
		with self.assertRaises(frappe.PermissionError):
			claims.set_claim_progress(non_rfs["name"], "Awaiting Customer")
