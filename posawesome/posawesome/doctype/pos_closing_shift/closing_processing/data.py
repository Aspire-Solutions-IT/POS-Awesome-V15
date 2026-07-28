import frappe
from frappe.utils import cint
from posawesome.posawesome.doctype.pos_closing_shift.closing_processing.invoices import submit_printed_invoices


def resolve_shift_sales_doctype(pos_opening_shift, pos_profile=None):
    if not pos_profile:
        pos_profile = frappe.db.get_value("POS Opening Shift", pos_opening_shift, "pos_profile")

    if cint(frappe.db.get_value("POS Profile", pos_profile, "posa_create_only_sales_order")):
        return "Sales Order"

    use_pos_invoice = frappe.db.get_value(
        "POS Profile",
        pos_profile,
        "create_pos_invoice_instead_of_sales_invoice",
    )
    return "POS Invoice" if use_pos_invoice else "Sales Invoice"

@frappe.whitelist()
def get_cashiers(doctype, txt, searchfield, start, page_len, filters):
    cashiers_list = frappe.get_all("POS Profile User", filters=filters, fields=["user"])
    result = []
    for cashier in cashiers_list:
        user_email = frappe.get_value("User", cashier.user, "email")
        if user_email:
            # Return list of tuples in format (value, label) where value is user ID and label shows both ID and email
            result.append([cashier.user, f"{cashier.user} ({user_email})"])
    return result


@frappe.whitelist()
def get_pos_invoices(pos_opening_shift, doctype=None, submit_printed=1):
    if not doctype:
        doctype = resolve_shift_sales_doctype(pos_opening_shift)

    if doctype == "Sales Order":
        opening_shift = frappe.get_doc("POS Opening Shift", pos_opening_shift)
        filters = {
            "docstatus": 1,
            "company": opening_shift.company,
            "pos_profile": opening_shift.pos_profile,
            "is_pos": 1,
            "creation": ["between", [opening_shift.period_start_date, frappe.utils.now_datetime()]],
        }
        orders = frappe.get_all("Sales Order", filters=filters, fields=["name"], order_by="creation asc")
        return [frappe.get_doc("Sales Order", d.name).as_dict() for d in orders]

    if cint(submit_printed):
        submit_printed_invoices(pos_opening_shift, doctype)
    cond = " and ifnull(consolidated_invoice,'') = ''" if doctype == "POS Invoice" else ""
    data = frappe.db.sql(
        f"""
	select
		name
	from
		`tab{doctype}`
	where
		docstatus = 1 and posa_pos_opening_shift = %s{cond}
	""",
        (pos_opening_shift),
        as_dict=1,
    )

    data = [frappe.get_doc(doctype, d.name).as_dict() for d in data]

    return data


@frappe.whitelist()
def get_payments_entries(pos_opening_shift):
    return frappe.get_all(
        "Payment Entry",
        filters={
            "docstatus": 1,
            "reference_no": pos_opening_shift,
            "payment_type": ["in", ["Receive", "Pay"]],
        },
        fields=[
            "name",
            "mode_of_payment",
            "paid_amount",
            "base_paid_amount",
            "paid_from_account_currency",
            "paid_to_account_currency",
            "target_exchange_rate",
            "reference_no",
            "posting_date",
            "party",
            "payment_type",
        ],
    )
