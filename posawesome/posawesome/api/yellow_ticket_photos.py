"""Yellow Ticket photos at the till.

Storage, Zoho WorkDrive upload and the phone page live in ``customer_due_dates.yellow_ticket_photos``.
This module only connects the POS checkout to it, and never lets it stop a sale:
linking runs inside a savepoint and any failure is logged, not raised.
"""

import json

import frappe
from frappe.utils import cint


def _is_installed():
    return "customer_due_dates" in frappe.get_installed_apps()


@frappe.whitelist(methods=["POST"])
def get_requirements(pos_profile, items=None):
    """Whether this till must take photos, the limits, and which basket lines need them.

    Both switches must be on: the POS Profile's own and the site-wide one in
    Yellow Ticket Photo Settings.
    """
    disabled = {"enabled": False, "min_photos": 0, "max_photos": 0, "row_refs": []}
    if not _is_installed():
        return disabled
    if not cint(frappe.db.get_value("POS Profile", pos_profile, "posa_require_yellow_ticket_photos")):
        return disabled

    from customer_due_dates.yellow_ticket_photos.api import get_till_requirements

    return get_till_requirements(pos_profile, items)


def _references_from_result(result, default_doctype):
    """(doctype, name) pairs for the documents a submit created, main one first."""
    if not isinstance(result, dict):
        return []
    doctype = result.get("doctype") or default_doctype
    names = [result.get("name")] if result.get("name") else []
    for created in result.get("created_sales_orders") or result.get("names") or []:
        name = created.get("name") if isinstance(created, dict) else created
        if name and name not in names:
            names.append(name)
    return [(doctype, name) for name in names if name]


def link_from_submission(data, result, default_doctype, pos_profile=None):
    """After a till sale is submitted, attach its Yellow Ticket photos to it.

    ``data`` is the submit payload; the till puts ``yellow_ticket_photos`` there:
    ``{"client_ref", "lines": [{"row_ref", "item_code", "item_name", "qty"}], "photos_owed"}``.
    Offline sales carry the same payload, so they link when they sync.
    """
    try:
        if isinstance(data, str):
            data = json.loads(data) if data.strip() else {}
        payload = (data or {}).get("yellow_ticket_photos")
        if not isinstance(payload, dict) or not payload.get("client_ref"):
            return
        if not _is_installed():
            return
        references = _references_from_result(result, default_doctype)
        if not references:
            return
    except Exception:
        frappe.log_error(title="Yellow Ticket photos: unreadable till payload")
        return

    frappe.db.savepoint("yellow_ticket_photo_link")
    try:
        from customer_due_dates.yellow_ticket_photos.service import link_session

        link_session(
            payload.get("client_ref"),
            references,
            lines=payload.get("lines") or [],
            photos_owed=cint(payload.get("photos_owed")),
            pos_profile=pos_profile,
        )
    except Exception:
        frappe.db.rollback(save_point="yellow_ticket_photo_link")
        frappe.log_error(
            title="Yellow Ticket photos could not be linked to the sale",
            reference_doctype=references[0][0],
            reference_name=references[0][1],
        )
