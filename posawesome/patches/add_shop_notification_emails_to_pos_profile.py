import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

FIELDS = [
	{
		"fieldname": "posa_section_notifications",
		"label": "Shop Notifications",
		"fieldtype": "Section Break",
		"insert_after": "posa_allow_select_print_format_in_payments",
	},
	{
		"fieldname": "posa_notification_emails",
		"label": "Notification Emails",
		"fieldtype": "Small Text",
		"description": (
			"Comma-separated email addresses to notify about this shop's events "
			"(e.g. payment links). Not yet wired to any notification -- this just "
			"holds the recipients for features built on top of it."
		),
		"insert_after": "posa_section_notifications",
	},
]


def execute():
	for field in FIELDS:
		cf_name = f"POS Profile-{field['fieldname']}"
		if not frappe.db.exists("Custom Field", cf_name):
			create_custom_field("POS Profile", field)
		else:
			frappe.db.set_value(
				"Custom Field",
				cf_name,
				{
					"label": field["label"],
					"fieldtype": field["fieldtype"],
					"description": field.get("description"),
					"insert_after": field["insert_after"],
				},
				update_modified=False,
			)
	frappe.clear_cache(doctype="POS Profile")
