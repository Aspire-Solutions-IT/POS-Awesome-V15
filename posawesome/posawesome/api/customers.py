# -*- coding: utf-8 -*-
# Copyright (c) 2020, Youssef Restom and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
import json
import frappe
from frappe.utils import nowdate, flt, cstr, get_datetime
from frappe import _
from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
    get_loyalty_program_details_with_points,
)
from frappe.utils.caching import redis_cache
from .utils import fetch_sales_person_names
from .stored_value import get_stored_value_summary

EXCLUDED_POS_CUSTOMER_NAMES = {"13682"}


def get_customer_groups(pos_profile):
    customer_groups = []
    if pos_profile.get("customer_groups"):
        # Get items based on the item groups defined in the POS profile
        for data in pos_profile.get("customer_groups"):
            group_name = data.get("customer_group") if data else None
            if not group_name:
                continue
            customer_groups.extend(
                [d.get("name") for d in get_child_nodes("Customer Group", group_name)]
            )

    return list(set(customer_groups))


def get_child_nodes(group_type, root):
    if not root:
        return []
    result = frappe.db.get_value(group_type, root, ["lft", "rgt"])
    if not result:
        return []
    lft, rgt = result
    return frappe.get_all(
        group_type,
        filters={"lft": [">=", lft], "rgt": ["<=", rgt]},
        fields=["name", "lft", "rgt"],
        order_by="lft",
    )


def get_customer_group_condition(pos_profile):
    cond = "disabled = 0"
    customer_groups = get_customer_groups(pos_profile)
    if customer_groups:
        escaped_groups = [frappe.db.escape(g) for g in customer_groups]
        cond = " customer_group in ({})".format(", ".join(escaped_groups))

    return cond


def _get_rfs_customer_filters(pos_profile, modified_after=None, start_after=None):
    filters = {"disabled": 0, "rfs_customer": 1}

    customer_groups = get_customer_groups(pos_profile)
    if customer_groups:
        filters["customer_group"] = ["in", customer_groups]

    if modified_after:
        try:
            parsed_modified_after = get_datetime(modified_after)
        except Exception:
            frappe.throw(_("modified_after must be a valid ISO datetime"))
        filters["modified"] = [">", parsed_modified_after.isoformat()]

    if start_after:
        filters["name"] = [">", start_after]

    return filters


def _exclude_hidden_pos_customers(rows):
    return [
        row
        for row in (rows or [])
        if cstr((row or {}).get("name")).strip() not in EXCLUDED_POS_CUSTOMER_NAMES
    ]


@frappe.whitelist()
def get_customer_balance(customer):
    if not customer:
        return {"balance": 0, "customer_name": None}

    try:
        customer_doc = frappe.get_doc("Customer", customer)
        customer_name = customer_doc.customer_name

        balance = frappe.db.sql(
            """
            SELECT SUM(debit - credit) AS balance
            FROM `tabGL Entry`
            WHERE party_type = 'Customer' AND party = %s AND docstatus = 1
        """,
            (customer,),
            as_dict=True,
        )

        return {
            "balance": flt(balance[0].get("balance", 0)) if balance else 0,
            "customer_name": customer_name,
        }
    except Exception as e:
        frappe.log_error(f"Error fetching customer balance: {e}")
        return {"balance": 0, "customer_name": None}


@frappe.whitelist()
def get_customer_names(pos_profile, limit=None, offset=None, start_after=None, modified_after=None):
    _pos_profile = json.loads(pos_profile)
    ttl = _pos_profile.get("posa_server_cache_duration")
    if ttl:
        ttl = int(ttl) * 60

    @redis_cache(ttl=ttl or 1800)
    def __get_customer_names(pos_profile, limit=None, offset=None, start_after=None, modified_after=None):
        return _get_customer_names(pos_profile, limit, offset, start_after, modified_after)

    def _get_customer_names(pos_profile, limit=None, offset=None, start_after=None, modified_after=None):
        pos_profile = json.loads(pos_profile)
        filters = _get_rfs_customer_filters(
            pos_profile,
            modified_after=modified_after,
            start_after=start_after,
        )

        customers = frappe.get_all(
            "Customer",
            filters=filters,
            fields=[
                "name",
                "mobile_no",
                "email_id",
                "tax_id",
                "customer_name",
                "primary_address",
            ],
            order_by="name",
            limit_start=None if start_after else offset,
            limit_page_length=limit,
        )
        return _exclude_hidden_pos_customers(customers)

    if _pos_profile.get("posa_use_server_cache") and not (limit or offset or start_after or modified_after):
        return __get_customer_names(pos_profile, limit, offset, start_after, modified_after)
    else:
        return _get_customer_names(pos_profile, limit, offset, start_after, modified_after)


@frappe.whitelist()
def get_customers_count(pos_profile):
    pos_profile = json.loads(pos_profile)
    filters = _get_rfs_customer_filters(pos_profile)
    count = frappe.db.count("Customer", filters)
    if not EXCLUDED_POS_CUSTOMER_NAMES:
        return count

    hidden_count = len(
        frappe.get_all(
            "Customer",
            filters={**filters, "name": ["in", list(EXCLUDED_POS_CUSTOMER_NAMES)]},
            pluck="name",
        )
        or []
    )
    return max(0, count - hidden_count)


@frappe.whitelist()
def get_customer_info(customer=None, company=None):
    customer = cstr(customer or "").strip()
    if not customer:
        return {}

    customer = frappe.get_doc("Customer", customer)

    res = {"loyalty_points": None, "conversion_factor": None}

    res["email_id"] = customer.email_id
    res["mobile_no"] = customer.mobile_no
    res["image"] = customer.image
    res["loyalty_program"] = customer.loyalty_program
    res["customer_price_list"] = customer.default_price_list
    res["customer_group"] = customer.customer_group
    res["customer_type"] = customer.customer_type
    res["territory"] = customer.territory
    res["birthday"] = customer.posa_birthday
    res["gender"] = customer.gender
    res["tax_id"] = customer.tax_id
    res["posa_discount"] = customer.posa_discount
    res["name"] = customer.name
    res["customer_name"] = customer.customer_name
    res["customer_group_price_list"] = frappe.get_value(
        "Customer Group", customer.customer_group, "default_price_list"
    )

    effective_price_list = (
        res.get("customer_price_list")
        or res.get("customer_group_price_list")
    )
    if effective_price_list:
        res["price_list_currency"] = frappe.get_value(
            "Price List", effective_price_list, "currency"
        )
    else:
        res["price_list_currency"] = None

    if customer.loyalty_program:
        lp_details = get_loyalty_program_details_with_points(
            customer.name,
            customer.loyalty_program,
            silent=True,
            include_expired_entry=False,
        )
        res["loyalty_points"] = lp_details.get("loyalty_points")
        res["conversion_factor"] = lp_details.get("conversion_factor")

    company = cstr(company or "").strip()
    if company:
        stored_value = get_stored_value_summary(customer=customer.name, company=company)
        res["stored_value_balance"] = stored_value.get("available_amount", 0)
        res["stored_value_sources"] = stored_value.get("source_count", 0)
    else:
        res["stored_value_balance"] = 0
        res["stored_value_sources"] = 0

    addresses = frappe.db.sql(
        """
	SELECT
	    address.name as address_name,
	    address.address_line1,
	    address.address_line2,
	    address.city,
	    address.state,
	    address.country,
	    address.pincode,
	    address.email_id,
	    address.phone,
	    address.address_type
	FROM `tabAddress` address
	INNER JOIN `tabDynamic Link` link
	    ON (address.name = link.parent)
	WHERE
	    link.link_doctype = 'Customer'
	    AND link.link_name = %s
	    AND address.disabled = 0
	    AND address.address_type = 'Shipping'
	ORDER BY address.creation DESC
	LIMIT 1
	""",
        (customer.name,),
        as_dict=True,
    )

    if addresses:
        addr = addresses[0]
        res["address_line1"] = addr.address_line1 or ""
        res["address_line2"] = addr.address_line2 or ""
        res["city"] = addr.city or ""
        res["state"] = addr.state or ""
        res["country"] = addr.country or ""
        res["pincode"] = addr.pincode or ""
        res["address_email_id"] = addr.email_id or ""
        res["address_phone"] = addr.phone or ""

    return res


@frappe.whitelist()
def create_customer(
    customer_name,
    company,
    pos_profile_doc,
    customer_id=None,
    tax_id=None,
    mobile_no=None,
    email_id=None,
    referral_code=None,
    birthday=None,
    customer_group=None,
    territory=None,
    customer_type=None,
    gender=None,
    method="create",
    address_line1=None,
    address_line2=None,
    city=None,
    postcode=None,
    county=None,
    country=None,
):
    pos_profile = json.loads(pos_profile_doc)

    # Format birthday to MySQL compatible format (YYYY-MM-DD) if provided
    formatted_birthday = None
    if birthday:
        try:
            # Try to parse date in DD-MM-YYYY format
            if "-" in birthday:
                date_parts = birthday.split("-")
                if len(date_parts) == 3:
                    day, month, year = date_parts
                    formatted_birthday = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            # If format is already YYYY-MM-DD, use as is
            elif len(birthday) == 10 and birthday[4] == "-" and birthday[7] == "-":
                formatted_birthday = birthday
        except Exception:
            frappe.log_error(f"Error formatting birthday: {birthday}", "POS Awesome")

    if method == "create":
        is_exist = frappe.db.exists("Customer", {"customer_name": customer_name})
        if pos_profile.get("posa_allow_duplicate_customer_names") or not is_exist:
            resolved_customer_group = "Individual"
            resolved_territory = "All Territories"
            customer = frappe.get_doc(
                {
                    "doctype": "Customer",
                    "customer_name": customer_name,
                    "posa_referral_company": company,
                    "tax_id": tax_id,
                    "mobile_no": mobile_no,
                    "email_id": email_id,
                    "posa_referral_code": referral_code,
                    "posa_birthday": formatted_birthday,
                    "customer_type": customer_type,
                    "gender": gender,
                    "rfs_customer": 1,
                    "auto_allocate_sales_orders": 1,
                    "customer_group": resolved_customer_group,
                    "territory": resolved_territory,
                }
            )

            customer.save()

            if address_line1 or city or postcode or county:
                args = {
                    "name": f"{customer.customer_name} - Shipping",
                    "doctype": "Customer",
                    "customer": customer.name,
                    "address_line1": address_line1 or "",
                    "address_line2": address_line2 or "",
                    "city": city or "",
                    "state": county or "",
                    "pincode": postcode or "",
                    "email_id": email_id or "",
                    "phone": mobile_no or "",
                    "country": country or "",
                }
                make_address(json.dumps(args))

            return customer
        else:
            frappe.throw(_("Customer already exists"))

    elif method == "update":
        customer_doc = frappe.get_doc("Customer", customer_id)
        customer_doc.customer_name = customer_name
        customer_doc.tax_id = tax_id
        customer_doc.mobile_no = mobile_no
        customer_doc.email_id = email_id
        customer_doc.posa_referral_code = referral_code
        customer_doc.posa_birthday = formatted_birthday
        customer_doc.customer_type = customer_type
        customer_doc.gender = gender
        customer_doc.save()

        # ensure contact details are synced correctly
        if mobile_no:
            set_customer_info(customer_doc.name, "mobile_no", mobile_no)
        if email_id:
            set_customer_info(customer_doc.name, "email_id", email_id)

        existing_address_name = frappe.db.get_value(
            "Dynamic Link",
            {
                "link_doctype": "Customer",
                "link_name": customer_id,
                "parenttype": "Address",
            },
            "parent",
        )

        if existing_address_name:
            address_doc = frappe.get_doc("Address", existing_address_name)
            address_doc.address_line1 = address_line1 or ""
            address_doc.address_line2 = address_line2 or ""
            address_doc.city = city or ""
            address_doc.pincode = postcode or ""
            address_doc.state = county or ""
            address_doc.email_id = email_id or ""
            address_doc.phone = mobile_no or ""
            address_doc.country = country or ""
            address_doc.save()
        else:
            if address_line1 or city or postcode or county:
                args = {
                    "name": f"{customer_doc.customer_name} - Shipping",
                    "doctype": "Customer",
                    "customer": customer_doc.name,
                    "address_line1": address_line1 or "",
                    "address_line2": address_line2 or "",
                    "city": city or "",
                    "state": county or "",
                    "pincode": postcode or "",
                    "email_id": email_id or "",
                    "phone": mobile_no or "",
                    "country": country or "",
                }
                make_address(json.dumps(args))

        return customer_doc


@frappe.whitelist()
def set_customer_info(customer, fieldname, value=""):
    if fieldname == "loyalty_program":
        frappe.db.set_value("Customer", customer, "loyalty_program", value)

    contact = frappe.get_cached_value("Customer", customer, "customer_primary_contact") or ""

    if contact:
        contact_doc = frappe.get_doc("Contact", contact)
        if fieldname == "email_id":
            contact_doc.set("email_ids", [{"email_id": value, "is_primary": 1}])
            frappe.db.set_value("Customer", customer, "email_id", value)
        elif fieldname == "mobile_no":
            contact_doc.set("phone_nos", [{"phone": value, "is_primary_mobile_no": 1}])
            frappe.db.set_value("Customer", customer, "mobile_no", value)
        contact_doc.save()

    else:
        contact_doc = frappe.new_doc("Contact")
        contact_doc.first_name = customer
        contact_doc.is_primary_contact = 1
        contact_doc.is_billing_contact = 1
        if fieldname == "mobile_no":
            contact_doc.add_phone(value, is_primary_mobile_no=1, is_primary_phone=1)

        if fieldname == "email_id":
            contact_doc.add_email(value, is_primary=1)

        contact_doc.append("links", {"link_doctype": "Customer", "link_name": customer})

        contact_doc.flags.ignore_mandatory = True
        contact_doc.save()
        frappe.set_value("Customer", customer, "customer_primary_contact", contact_doc.name)


@frappe.whitelist()
def get_customer_addresses(customer):
    return frappe.db.sql(
        """
        SELECT
            address.name,
            address.address_line1,
            address.address_line2,
            address.address_title,
            address.city,
            address.state,
            address.country,
            address.pincode,
            address.email_id,
            address.phone,
            address.address_type
        FROM `tabAddress` as address
        INNER JOIN `tabDynamic Link` AS link
                                ON address.name = link.parent
        WHERE link.link_doctype = 'Customer'
            AND link.link_name = %s
            AND address.disabled = 0
        ORDER BY address.name
        """,
        (customer,),
        as_dict=1,
    )


@frappe.whitelist()
def get_store_collection_addresses():
    return frappe.get_all(
        "Address",
        filters={
            "disabled": 0,
            "posa_is_store_collection_point": 1,
        },
        fields=[
            "name",
            "address_line1",
            "address_line2",
            "address_title",
            "city",
            "state",
            "country",
            "pincode",
            "email_id",
            "phone",
            "address_type",
            "posa_is_store_collection_point",
        ],
        order_by="address_title asc, name asc",
    )


def _validate_store_collection_address(address_name):
    if not address_name:
        frappe.throw(_("Store collection address is required"))

    is_store_collection_point = frappe.db.get_value(
        "Address", address_name, "posa_is_store_collection_point"
    )
    if not is_store_collection_point:
        frappe.throw(_("Selected address is not a store collection point"))


def _first_value(*values):
    for value in values:
        normalized = cstr(value or "").strip()
        if normalized:
            return normalized
    return ""


def _get_customer_contact_details(customer):
    """Best-effort (phone, email) for a customer: the customer's primary
    address/contact first, falling back to any other linked address/contact
    that has a value."""
    phone = ""
    email = ""

    customer_fields = (
        frappe.db.get_value(
            "Customer",
            customer,
            ["customer_primary_address", "customer_primary_contact"],
            as_dict=True,
        )
        or {}
    )

    primary_address = customer_fields.get("customer_primary_address")
    if primary_address:
        address_phone, address_email = frappe.db.get_value(
            "Address", primary_address, ["phone", "email_id"]
        ) or ("", "")
        phone = _first_value(phone, address_phone)
        email = _first_value(email, address_email)

    primary_contact = customer_fields.get("customer_primary_contact")
    if primary_contact and (not phone or not email):
        contact_phone, contact_email = frappe.db.get_value(
            "Contact", primary_contact, ["phone", "email_id"]
        ) or ("", "")
        phone = _first_value(phone, contact_phone)
        email = _first_value(email, contact_email)

    if not phone or not email:
        for linked_address in frappe.get_all(
            "Dynamic Link",
            filters={
                "parenttype": "Address",
                "link_doctype": "Customer",
                "link_name": customer,
            },
            pluck="parent",
        ):
            if phone and email:
                break
            address_phone, address_email = frappe.db.get_value(
                "Address", linked_address, ["phone", "email_id"]
            ) or ("", "")
            phone = _first_value(phone, address_phone)
            email = _first_value(email, address_email)

    if not phone or not email:
        for linked_contact in frappe.get_all(
            "Dynamic Link",
            filters={
                "parenttype": "Contact",
                "link_doctype": "Customer",
                "link_name": customer,
            },
            pluck="parent",
        ):
            if phone and email:
                break
            contact_phone, contact_email = frappe.db.get_value(
                "Contact", linked_contact, ["phone", "email_id"]
            ) or ("", "")
            phone = _first_value(phone, contact_phone)
            email = _first_value(email, contact_email)

    return phone, email


def _get_existing_store_collection_copy(customer, source_address_name):
    """An Address previously cloned from source_address_name and already
    linked to this customer, if one exists."""
    rows = frappe.db.sql(
        """
        SELECT address.name AS address_name
        FROM `tabAddress` AS address
        INNER JOIN `tabDynamic Link` AS link
                ON link.parent = address.name
                AND link.parenttype = 'Address'
        WHERE address.posa_source_address = %s
            AND link.link_doctype = 'Customer'
            AND link.link_name = %s
        LIMIT 1
        """,
        (source_address_name, customer),
        as_dict=True,
    )
    return rows[0].address_name if rows else None


@frappe.whitelist()
def link_store_collection_address_to_customer(customer, address_name):
    """Link a customer to a store collection point without mutating the
    shared store Address record. A personal copy of the store address is
    created (carrying the customer's own phone/email where available) and
    that copy is linked to the customer instead."""
    customer = cstr(customer or "").strip()
    address_name = cstr(address_name or "").strip()

    if not customer:
        frappe.throw(_("Customer is required"))

    _validate_store_collection_address(address_name)

    existing_copy = _get_existing_store_collection_copy(customer, address_name)
    if existing_copy:
        return {
            "address_name": existing_copy,
            "source_address": address_name,
            "customer": customer,
            "linked": False,
            "already_linked": True,
        }

    source_address = frappe.db.get_value(
        "Address",
        address_name,
        [
            "address_title",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "country",
            "pincode",
            "address_type",
            "phone",
            "email_id",
        ],
        as_dict=True,
    ) or {}

    customer_phone, customer_email = _get_customer_contact_details(customer)
    phone = _first_value(customer_phone, source_address.get("phone"))
    email = _first_value(customer_email, source_address.get("email_id"))

    copy_doc = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": source_address.get("address_title"),
            "address_line1": source_address.get("address_line1"),
            "address_line2": source_address.get("address_line2"),
            "city": source_address.get("city"),
            "state": source_address.get("state"),
            "country": source_address.get("country"),
            "pincode": source_address.get("pincode"),
            "address_type": source_address.get("address_type") or "Shipping",
            "phone": phone,
            "email_id": email,
            "posa_is_store_collection_point": 0,
            "posa_source_address": address_name,
            "links": [{"link_doctype": "Customer", "link_name": customer}],
        }
    )
    copy_doc.insert()

    return {
        "address_name": copy_doc.name,
        "source_address": address_name,
        "customer": customer,
        "linked": True,
        "already_linked": False,
    }


@frappe.whitelist()
def make_address(args):
    if isinstance(args, str):
        args = json.loads(args)
    args = args or {}
    address = frappe.get_doc(
        {
            "doctype": "Address",
            "address_title": args.get("name"),
            "address_line1": args.get("address_line1"),
            "address_line2": args.get("address_line2"),
            "city": args.get("city"),
            "state": args.get("state"),
            "pincode": args.get("pincode"),
            "email_id": args.get("email_id"),
            "phone": args.get("phone"),
            "country": args.get("country"),
            "address_type": args.get("address_type") or "Shipping",
            "links": [{"link_doctype": args.get("doctype"), "link_name": args.get("customer")}],
        }
    ).insert()

    return address


@frappe.whitelist()
def get_sales_person_names(pos_profile=None):
    return fetch_sales_person_names(pos_profile=pos_profile)
