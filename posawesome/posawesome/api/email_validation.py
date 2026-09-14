import frappe
from frappe import _
from frappe.utils import cstr, split_emails, validate_email_address


def validate_optional_email(value):
    """Return a normalized single email, or an empty string for an optional field."""
    email = cstr(value or "").strip()
    if not email:
        return ""

    validated = validate_email_address(email, throw=False)
    addresses = split_emails(validated)
    if len(addresses) != 1 or addresses[0] != email:
        frappe.throw(_("{0} is not a valid email address.").format(email), frappe.ValidationError)

    return addresses[0]
