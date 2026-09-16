"""POSAwesome-facing endpoints for the Customer Claims process.

These are thin, permission-checked wrappers over the shared
``customer_due_dates.customer_claims`` module. POSAwesome owns the presentation
(raising a claim from Sales Order Management, and a filterable Claims screen);
the claims app still owns every rule, workflow transition and validation.
"""

import base64
import binascii

import frappe
from customer_due_dates.customer_claims import workspace as claim_workspace
from customer_due_dates.customer_claims.api import get_order_items
from frappe import _
from frappe.utils import cstr

from posawesome.posawesome.api.employees import _get_terminal_users

PREFERRED_OUTCOMES = ("Exchange", "Refund", "Credit", "Replace", "Service Call")
SERVICE_CALL_TYPES = ("Maintenance Visit", "Spare Part")
# Evidence is a photo or a scanned document from the shop floor, kept small.
EVIDENCE_MAX_BYTES = 15 * 1024 * 1024
EVIDENCE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".pdf")


def _require_claim_create():
	frappe.has_permission("Customer Claim", ptype="create", throw=True)


def _is_rfs_order(sales_order):
	"""POSAwesome only handles claims for RFS (ready-for-supply) Sales Orders."""
	return bool(sales_order) and bool(
		frappe.db.get_value("Sales Order", sales_order, "rfs_order")
	)


def _require_rfs_order(sales_order):
	if not _is_rfs_order(sales_order):
		frappe.throw(
			_("Claims in POSAwesome are only available for RFS Sales Orders."),
			frappe.PermissionError,
		)


@frappe.whitelist()
def get_sales_order_claim_context(sales_order):
	"""Everything the Raise Claim dialog needs for one Sales Order.

	Returns the order's claimable lines, the enabled claim types (with their
	evidence rules), the fixed outcome/service option lists, and any claims that
	already exist against this order so the user can be warned about an overlap.
	"""
	_require_claim_create()
	_require_rfs_order(sales_order)
	context = get_order_items(sales_order)

	claim_types = frappe.get_list(
		"Customer Claim Type",
		filters={"disabled": 0},
		fields=["name", "claim_type_name", "evidence_required", "evidence_instructions"],
		order_by="claim_type_name",
		limit=0,
	)

	existing = frappe.get_list(
		"Customer Claim",
		filters={"sales_order": sales_order},
		fields=[
			"name",
			"workflow_state",
			"progress",
			"claim_type",
			"preferred_outcome",
			"description",
			"creation",
		],
		order_by="creation desc",
		limit=0,
	)
	if existing:
		covered = frappe.get_all(
			"Customer Claim Item",
			filters={"parent": ["in", [row.name for row in existing]]},
			fields=["parent", "sales_order_item", "item_code", "qty"],
			limit=0,
		)
		by_claim = {}
		for row in covered:
			by_claim.setdefault(row.parent, []).append(
				{"sales_order_item": row.sales_order_item, "item_code": row.item_code, "qty": row.qty}
			)
		for claim in existing:
			claim["items"] = by_claim.get(claim.name, [])

	return dict(
		customer=context["customer"],
		company=context["company"],
		currency=context["currency"],
		items=context["items"],
		claim_types=claim_types,
		existing_claims=existing,
		preferred_outcomes=list(PREFERRED_OUTCOMES),
		service_call_types=list(SERVICE_CALL_TYPES),
	)


@frappe.whitelist(methods=["POST"])
def upload_claim_evidence(filename, content_base64):
	"""Store one evidence file for a claim and return its URL.

	POSAwesome sends the photo as base64 through the normal RPC channel (which
	already carries the CSRF token), rather than a multipart form. The file is
	private and unattached; ``raise_claim`` records its URL on the new claim.
	"""
	_require_claim_create()

	safe_name = cstr(filename).strip() or "evidence"
	if "." not in safe_name or safe_name.lower().rsplit(".", 1)[-1] not in (
		ext.lstrip(".") for ext in EVIDENCE_EXTENSIONS
	):
		frappe.throw(_("Evidence must be a photo or a PDF."))

	try:
		content = base64.b64decode(str(content_base64), validate=True)
	except (binascii.Error, ValueError):
		frappe.throw(_("The evidence file could not be read. Try again."))
	if not content:
		frappe.throw(_("The evidence file is empty."))
	if len(content) > EVIDENCE_MAX_BYTES:
		frappe.throw(_("Evidence files must be under 15 MB."))

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": safe_name,
			"is_private": 1,
			"content": content,
		}
	).insert()
	return {"file_url": file_doc.file_url, "file_name": file_doc.file_name}


def _resolve_pos_actor(pos_profile, requested_user):
	"""The POS cashier actually raising this claim, not the shared terminal's
	own Frappe login -- many branches share one ERP session across staff and
	pick the real operator via the till's own cashier switch. Falls back to
	the session user whenever there's nothing to attribute to, and
	re-validates the requested user against the POS Profile's own registered
	cashier roster (the same check the cashier switch itself uses) so this
	can't be used to attribute a claim to an arbitrary, unrelated user."""
	requested_user = (requested_user or "").strip()
	if not requested_user or requested_user == frappe.session.user:
		return frappe.session.user
	profile_name = (pos_profile or "").strip()
	if not profile_name or requested_user not in _get_terminal_users(profile_name):
		return frappe.session.user
	return requested_user


@frappe.whitelist(methods=["POST"])
def raise_claim(payload):
	"""Create a claim from POSAwesome and submit it for approval.

	Delegates to the claims workspace so evidence rules, item ownership and the
	real Workflow transition all run exactly as they do on the Desk. Attributed
	to the POS cashier actually running the till (see _resolve_pos_actor), not
	the shared terminal's own login: both `assigned_to` (the claim's own
	"Claim Owner" field) and the record's `owner` ("Raised by") end up as that
	cashier. `owner` can't be set through the normal insert path -- Frappe's
	own `set_user_and_timestamp` always forces it to the real session user
	there, by design -- so it's corrected afterwards with an explicit,
	validated `db_set` once the claim exists.

	`acting_as=cashier` also makes auto-approval follow the cashier's own role,
	not the shared terminal session's -- a Desk/POS terminal login can hold
	Claim Approver (needed to administer the till) even when the cashier
	actually raising the claim only holds Claim User, and without this a claim
	raised by a plain Claim User cashier would wrongly auto-approve itself
	just because of who the terminal happens to be logged in as.
	"""
	parsed = frappe.parse_json(payload)
	if not isinstance(parsed, dict):
		return claim_workspace.create_claim(payload)
	_require_rfs_order(parsed.get("sales_order"))
	cashier = _resolve_pos_actor(parsed.get("pos_profile"), parsed.get("assigned_to"))
	parsed["assigned_to"] = cashier
	result = claim_workspace.create_claim(parsed, acting_as=cashier)
	if cashier != frappe.session.user:
		frappe.db.set_value("Customer Claim", result["name"], "owner", cashier, update_modified=False)
	return result


@frappe.whitelist()
def get_sales_order_claim_summary(sales_order):
	"""How many claims (readable by this user) exist for one RFS Sales Order.

	Used by Sales Order Management to decide whether to offer a "Show claims"
	shortcut. Non-RFS orders report zero so the shortcut stays hidden.
	"""
	_require_claim_create()
	if not _is_rfs_order(sales_order):
		return {"count": 0}
	rows = frappe.get_list(
		"Customer Claim",
		filters={"sales_order": sales_order},
		fields=["name"],
		limit=0,
	)
	return {"count": len(rows)}


@frappe.whitelist()
def list_claims(
	search="",
	approval="",
	progress="",
	assigned_to="",
	claim_type="",
	sales_order="",
	open_only=0,
	start=0,
):
	"""Filterable claims overview for the POSAwesome Claims screen (RFS orders only)."""
	return claim_workspace.get_overview(
		search=search,
		approval=approval,
		progress=progress,
		assigned_to=assigned_to,
		claim_type=claim_type,
		sales_order=sales_order,
		rfs_only=1,
		open_only=open_only,
		start=start,
	)


@frappe.whitelist()
def get_claim(claim):
	"""Full detail for one claim on an RFS order: facts, items, decisions, actions."""
	data = claim_workspace.get_detail(claim)
	_require_rfs_order((data.get("claim") or {}).get("sales_order"))
	return data


def _require_rfs_claim(claim):
	sales_order = frappe.db.get_value("Customer Claim", claim, "sales_order")
	_require_rfs_order(sales_order)


@frappe.whitelist(methods=["POST"])
def propose_decision(payload):
	"""Record a resolution decision for a claim on an RFS order.

	Always goes to Pending Approval, never auto-approves (require_approval=True)
	-- a shared POS terminal's own Frappe login can hold Claim Approver even
	when there's no reliable way to know which specific person at the till is
	actually proposing this decision, so it must always be reviewed by a real
	Desk user before it takes effect.
	"""
	parsed = frappe.parse_json(payload)
	if isinstance(parsed, dict):
		_require_rfs_claim(parsed.get("claim"))
	return claim_workspace.create_decision(payload, require_approval=True)


@frappe.whitelist(methods=["POST"])
def set_claim_progress(claim, progress, modified=""):
	"""Move an RFS claim along one of the allowed manual progress steps."""
	_require_rfs_claim(claim)
	return claim_workspace.set_claim_progress(claim, progress, modified)
