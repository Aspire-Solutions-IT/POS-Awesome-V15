declare const frappe: any;

interface BuildReceiptPdfUrlOptions {
	name: string;
	profile?: Record<string, any> | null;
	doctype?: string;
}

/**
 * URL for the printable POS receipt PDF.
 *
 * Deliberately not the `/printview` URL that usePaymentPrinting builds: that one
 * honours the silent-print/QZ profile settings and renders HTML, whereas the till
 * needs a PDF page it can hand to the browser's own print dialog. It also routes
 * through customer_due_dates' download_pdf override, which applies the Print Format
 * Overrides page height/width, so receipt-roll dimensions come out right.
 *
 * No `key` is sent: the operator is printing from an authenticated session, and
 * `key` exists for unauthenticated access.
 */
export function buildReceiptPdfUrl({
	name,
	profile,
	doctype = "Sales Order",
}: BuildReceiptPdfUrlOptions) {
	// Same format the receipt is emailed in, so the printed and emailed copies
	// match; the generic print formats are only a fallback for profiles that
	// never configured the receipt email.
	const format =
		profile?.posa_receipt_email_print_format ||
		profile?.print_format_for_online ||
		profile?.print_format ||
		"";

	const params = new URLSearchParams({
		doctype,
		name,
		no_letterhead: "0",
	});

	// Omitted rather than sent empty so the server falls back to the Standard
	// format instead of looking up one named "".
	if (format) {
		params.set("format", format);
	}

	if (profile?.letter_head) {
		params.set("letterhead", profile.letter_head);
	}

	return `${frappe.urllib.get_base_url()}/api/method/frappe.utils.print_format.download_pdf?${params.toString()}`;
}

export function openReceiptPdf(options: BuildReceiptPdfUrlOptions) {
	window.open(buildReceiptPdfUrl(options), "_blank", "noopener,noreferrer");
}
