# Copyright (c) 2022, Youssef Restom and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint
import json
from frappe.model.document import Document


class DeliveryCharges(Document):
    def validate(self):
        if self.default_rate is None or self.default_rate == "":
            frappe.throw(_("Default Rate is required"))
        if self.default_rate < 0:
            frappe.throw(_("Default Rate cannot be negative"))
        self.validate_profiles()

    def validate_profiles(self):
        profiles = []
        for row in self.profiles:
            if row.pos_profile not in profiles:
                profiles.append(row.pos_profile)
            else:
                frappe.throw("Duplicate POS Profile in Delivery Charges")
        self.set_profiles_list(profiles)

    def set_profiles_list(self, profiles_list):
        if len(profiles_list) > 0:
            self.profiles_list = json.dumps(profiles_list)
        else:
            self.profiles_list = None


def get_applicable_delivery_charges(
    company,
    pos_profile=None,
    customer=None,
    address=None,
    delivery_charges=None,
    restrict=False,
):
    charges = []
    address_list = []
    delivery_charges_list = []
    if address:
        address_list.append(address)
    if customer:
        address_list.extend(
            frappe.get_all(
                "Dynamic Link",
                filters={
                    "link_doctype": "Customer",
                    "link_name": customer,
                    "parentfield": "links",
                    "parenttype": "Address",
                },
                pluck="parent",
            )
        )
    for address in address_list:
        address_charges = frappe.get_cached_value("Address", address, "posa_delivery_charges")
        if address_charges:
            delivery_charges_list.append(address_charges)

    delivery_charges_filters = {"disabled": 0, "company": company}
    if delivery_charges:
        delivery_charges_list.append(delivery_charges)

    if len(delivery_charges_list) > 0:
        delivery_charges_filters["name"] = ["in", delivery_charges_list]
    if restrict:
        delivery_charges_filters["profiles_list"] = ["not in", ["", None]]

    delivery_charges_items = frappe.get_all(
        "Delivery Charges",
        filters=delivery_charges_filters,
        fields=["*"],
    )
    delivery_charges_list = [i.name for i in delivery_charges_items]

    delivery_profiels_filters = {"parent": ("in", delivery_charges_list)}
    if pos_profile:
        delivery_profiels_filters["pos_profile"] = pos_profile
    delivery_profiels = frappe.get_all(
        "Delivery Charges POS Profile",
        filters=delivery_profiels_filters,
        fields=["*"],
    )
    for charge in delivery_charges_items:
        profile = next((i for i in delivery_profiels if i.parent == charge.name), None)
        if profile:
            charge.rate = profile.rate
            charges.append(charge)
        else:
            if not restrict:
                if not charge.profiles_list:
                    charge.rate = charge.default_rate
                    charges.append(charge)

    try:
        from posawesome.posawesome.api.charge_pricing import _is_partner_mode, filter_available
    except ImportError:
        # charge_pricing imports customer_due_dates at module level, so the shared
        # availability rule is unavailable. A standalone install offers every charge as
        # before AP-1, but a partner must never be offered a staff-only charge.
        _is_partner_mode = None
        available = _partner_safe(charges)
    else:
        available = filter_available(charges)

    mark_default = None
    if _is_partner_mode is not None and frappe.db.has_column("Delivery Charges", "default_for"):
        try:
            from customer_due_dates.selling.pos_availability import mark_default
        except ImportError:
            # customer_due_dates predates mark_default.
            mark_default = None

    if mark_default is None:
        # Old customer_due_dates, customer_due_dates missing, or the default_for column not
        # created yet: keep the legacy is_default checkbox as stored.
        for charge in available:
            charge["is_default"] = 1 if cint(charge.get("is_default")) else 0
        return _without_default_for(_with_order_type_name(available))

    return _without_default_for(_with_order_type_name(mark_default(available, _is_partner_mode())))


PARTNER_AVAILABLE_TO = ("Agile only", "Both")


def _partner_safe(charges):
    """Fallback when customer_due_dates is missing: keep audience filtering in partner mode."""
    try:
        from posawesome.posawesome.api.partner_gate import is_partner_user
    except ImportError:
        return charges
    if not is_partner_user():
        return charges
    # Same rule as customer_due_dates is_available(..., partner_mode=True); a blank value
    # means "TFW only", so it is hidden.
    return [c for c in charges if c.get("available_to") in PARTNER_AVAILABLE_TO]


def _with_order_type_name(charges):
    """Add ``order_type_name`` (e.g. "DHD"): ``order_type`` is a generated Order Type id.

    The POS shows the delivery address form for a DHD charge, so it needs the name.
    """
    ids = {c.get("order_type") for c in charges if c.get("order_type")}
    names = {}
    if ids:
        names = {
            r.name: r.order_type_name
            for r in frappe.get_all(
                "Order Type", filters={"name": ["in", list(ids)]}, fields=["name", "order_type_name"]
            )
        }
    for charge in charges:
        charge["order_type_name"] = names.get(charge.get("order_type")) or ""
    return charges


def _without_default_for(charges):
    """The POS only needs the computed ``is_default``; ``default_for`` is not for partners."""
    for charge in charges:
        charge.pop("default_for", None)
    return charges
