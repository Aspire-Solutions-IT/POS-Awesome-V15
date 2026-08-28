# -*- coding: utf-8 -*-
# Copyright (c) 2020, Youssef Restom and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe.utils import cint, nowdate
from frappe import _
from .utilities import get_version
from .employees import (
    _ensure_terminal_user,
    _get_user_doc,
    _get_user_pin,
    _is_pos_supervisor,
    _resolve_profile_name,
)

OPEN_SHIFT_FILTERS = {
    "pos_closing_shift": ["is", "not set"],
    "docstatus": 1,
    "status": "Open",
}


def _get_user_pos_profiles(user=None):
    """POS Profiles the user is assigned to via the POS Profile User child table."""
    user = user or frappe.session.user
    return frappe.db.sql(
        """
        SELECT DISTINCT p.name, p.company, p.currency 
        FROM `tabPOS Profile` p
        INNER JOIN `tabPOS Profile User` u ON u.parent = p.name
        WHERE p.disabled = 0 AND u.user = %s
        ORDER BY p.name
    """,
        user,
        as_dict=1,
    )


def _get_payment_methods_for_profiles(pos_profiles_list):
    """Opening-balance payment rows for the given profiles, stamped with each profile's currency."""
    if not pos_profiles_list:
        return []

    payment_method_table = "POS Payment Method" if get_version() == 13 else "Sales Invoice Payment"
    payments_method = frappe.get_list(
        payment_method_table,
        filters={"parent": ["in", pos_profiles_list]},
        fields=["*"],
        limit_page_length=0,
        order_by="parent",
        ignore_permissions=True,
    )
    # set currency from pos profile
    for mode in payments_method:
        mode["currency"] = frappe.get_cached_value("POS Profile", mode["parent"], "currency")
    return payments_method


def _get_open_shifts(user, pos_profile=None):
    """Open opening shifts for a user, newest first. Optionally scoped to one profile."""
    filters = dict(OPEN_SHIFT_FILTERS)
    filters["user"] = user
    if pos_profile:
        filters["pos_profile"] = pos_profile
    return frappe.db.get_all(
        "POS Opening Shift",
        filters=filters,
        fields=["name", "pos_profile"],
        order_by="period_start_date desc",
    )


def _create_opening_shift(pos_profile, company, balance_details):
    if isinstance(balance_details, str):
        balance_details = json.loads(balance_details)

    new_pos_opening = frappe.get_doc(
        {
            "doctype": "POS Opening Shift",
            "period_start_date": frappe.utils.get_datetime(),
            "posting_date": frappe.utils.getdate(),
            "user": frappe.session.user,
            "pos_profile": pos_profile,
            "company": company,
            "docstatus": 1,
        }
    )
    new_pos_opening.set("balance_details", balance_details or [])
    new_pos_opening.insert(ignore_permissions=True)
    return new_pos_opening


@frappe.whitelist()
def get_opening_dialog_data():
    data = {}

    # Get only POS Profiles where current user is defined in POS Profile User table
    pos_profiles_data = _get_user_pos_profiles()

    data["pos_profiles_data"] = pos_profiles_data

    # Derive companies from accessible POS Profiles
    company_names = []
    for profile in pos_profiles_data:
        if profile.company and profile.company not in company_names:
            company_names.append(profile.company)
    data["companies"] = [{"name": c} for c in company_names]

    pos_profiles_list = []
    for i in data["pos_profiles_data"]:
        pos_profiles_list.append(i.name)

    data["payments_method"] = _get_payment_methods_for_profiles(pos_profiles_list)

    return data


@frappe.whitelist()
def create_opening_voucher(pos_profile, company, balance_details):
    balance_details = json.loads(balance_details)

    new_pos_opening = _create_opening_shift(pos_profile, company, balance_details)

    data = {}
    data["pos_opening_shift"] = new_pos_opening.as_dict()
    update_opening_shift_data(data, new_pos_opening.pos_profile)
    return data


@frappe.whitelist()
def check_opening_shift(user, preferred_shift=None):
    """Return the user's active opening shift.

    A user may hold one open shift per POS Profile (see ``switch_pos_profile``), so
    "newest" is not necessarily "active". When the terminal knows which shift it was
    last operating, it passes ``preferred_shift`` and that one wins as long as it is
    still open. Otherwise the newest open shift is returned, as before.
    """
    open_vouchers = _get_open_shifts(user)
    data = ""
    if len(open_vouchers) > 0:
        selected = None
        preferred_shift = str(preferred_shift or "").strip()
        if preferred_shift:
            for voucher in open_vouchers:
                if voucher["name"] == preferred_shift:
                    selected = voucher
                    break
        if not selected:
            selected = open_vouchers[0]

        data = {}
        data["pos_opening_shift"] = frappe.get_doc("POS Opening Shift", selected["name"])
        update_opening_shift_data(data, selected["pos_profile"])
    return data


@frappe.whitelist()
def get_switchable_pos_profiles():
    """POS Profiles the current user may switch to, and whether each already has an open shift."""
    user = frappe.session.user
    pos_profiles_data = _get_user_pos_profiles(user)

    open_shift_by_profile = {}
    for voucher in _get_open_shifts(user):
        # _get_open_shifts is newest first, so the first row per profile is the live one.
        open_shift_by_profile.setdefault(voucher["pos_profile"], voucher["name"])

    profiles = []
    needs_balance = []
    for profile in pos_profiles_data:
        open_shift = open_shift_by_profile.get(profile.name)
        profiles.append(
            {
                "name": profile.name,
                "company": profile.company,
                "currency": profile.currency,
                "open_shift": open_shift,
            }
        )
        if not open_shift:
            needs_balance.append(profile.name)

    return {
        "pos_profiles_data": profiles,
        "payments_method": _get_payment_methods_for_profiles(needs_balance),
    }


def _validate_switch_supervisor(current_profile, supervisor_user, pin):
    """A profile switch must be authorised by a supervisor assigned to the current terminal."""
    profile_name = _resolve_profile_name(current_profile)
    if not profile_name:
        frappe.throw(_("Current POS profile is required to authorise a profile switch."))

    supervisor_user = str(supervisor_user or "").strip()
    pin = str(pin or "").strip()
    if not supervisor_user or not pin:
        frappe.throw(_("Supervisor and PIN are required to switch POS profile."))

    _ensure_terminal_user(profile_name, supervisor_user)
    user_doc = _get_user_doc(supervisor_user)

    stored_pin = _get_user_pin(user_doc)
    if not stored_pin or stored_pin != pin:
        frappe.throw(_("Invalid supervisor PIN."))

    if not _is_pos_supervisor(user_doc):
        frappe.throw(_("Only POS supervisors can switch POS profile without closing the shift."))

    return user_doc


@frappe.whitelist()
def switch_pos_profile(
    target_profile,
    current_profile=None,
    balance_details=None,
    supervisor_user=None,
    pin=None,
):
    """Move the terminal to another POS Profile without closing the current shift.

    The outgoing shift is left open and untouched, so each profile's invoices stay
    attached to their own opening shift and closing reconciliation is unaffected.
    An existing open shift for the target profile is resumed rather than duplicated.

    Returns the same payload shape as ``check_opening_shift`` so the frontend can feed
    it straight into its existing register-data path.
    """
    user = frappe.session.user

    target_profile = _resolve_profile_name(target_profile)
    if not target_profile:
        frappe.throw(_("Select a POS profile to switch to."))

    allowed_profiles = {profile.name: profile for profile in _get_user_pos_profiles(user)}
    if target_profile not in allowed_profiles:
        frappe.throw(_("You are not assigned to the selected POS profile."))

    if _resolve_profile_name(current_profile) == target_profile:
        frappe.throw(_("You are already on this POS profile."))

    _validate_switch_supervisor(current_profile, supervisor_user, pin)

    existing_shifts = _get_open_shifts(user, pos_profile=target_profile)
    if existing_shifts:
        opening_shift = frappe.get_doc("POS Opening Shift", existing_shifts[0]["name"])
    else:
        # Take the company from the profile itself rather than the client, so it can
        # never disagree with POSOpeningShift.validate_pos_profile_and_cashier.
        opening_shift = _create_opening_shift(
            target_profile,
            allowed_profiles[target_profile].company,
            balance_details,
        )

    data = {}
    data["pos_opening_shift"] = opening_shift.as_dict()
    update_opening_shift_data(data, target_profile)
    return data


def update_opening_shift_data(data, pos_profile):
    data["pos_profile"] = frappe.get_doc("POS Profile", pos_profile)
    if data["pos_profile"].get("posa_language"):
        frappe.local.lang = data["pos_profile"].posa_language
    data["company"] = frappe.get_doc("Company", data["pos_profile"].company)
    allow_negative_stock = cint(frappe.db.get_single_value("Stock Settings", "allow_negative_stock") or 0)
    data["stock_settings"] = {}
    data["stock_settings"].update({"allow_negative_stock": bool(allow_negative_stock)})
