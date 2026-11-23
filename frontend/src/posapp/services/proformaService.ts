/**
 * Pro forma sending for partner orders (AP-12).
 *
 * The one place that talks to the server's `send_proforma`, so a change to that method
 * (POST only, resend semantics, new result fields) is a change here and nowhere else.
 * The result is read defensively: every field may be missing and a failed call never
 * throws, because the order is already saved by the time this runs and the POS must say
 * "order saved, pro forma not sent" and offer a retry rather than surface an exception.
 */

declare const frappe: any;

export const PAYMENT_TYPE_ON_ACCOUNT = "On Account";
export const PAYMENT_TYPE_PROFORMA = "Proforma";

const SEND_PROFORMA_METHOD = "posawesome.posawesome.api.sales_orders.send_proforma";

export type ProformaResult = {
	ok: boolean;
	link: string;
	emailSent: boolean;
	attachmentOk: boolean;
	error: string;
};

export type ProformaOutcome = {
	/** sent: emailed with the PDF. attachment_missing: emailed without it. link_only: not emailed. failed: no link. */
	state: "sent" | "attachment_missing" | "link_only" | "failed";
	level: "success" | "warning" | "error";
	message: string;
	canRetry: boolean;
};

const text = (value: unknown): string => (typeof value === "string" ? value.trim() : "");

const stripHtml = (value: string): string => value.replace(/<[^>]+>/g, "").trim();

/** Turns whatever the server (or a failed request) returned into a ProformaResult. */
export function normaliseProformaResponse(raw: any): ProformaResult {
	const message = raw && typeof raw === "object" && "message" in raw ? raw.message : raw;
	if (!message || typeof message !== "object") {
		return {
			ok: false,
			link: "",
			emailSent: false,
			attachmentOk: true,
			error: text(raw?._error_message) || "",
		};
	}
	return {
		ok: Boolean(message.ok),
		link: text(message.link),
		emailSent: Boolean(message.email_sent),
		attachmentOk: message.attachment_ok === undefined ? true : Boolean(message.attachment_ok),
		error: stripHtml(text(message.error)),
	};
}

/** Maps a result to what the operator is told. `email` is shown when known. */
export function describeProformaResult(
	result: ProformaResult,
	__: (_text: string, _args?: any[]) => string = (t) => t,
	email = "",
): ProformaOutcome {
	if (!result.ok) {
		return {
			state: "failed",
			level: "error",
			message:
				result.error ||
				__("The order was saved, but the pro forma could not be sent. Retry to send it again."),
			canRetry: true,
		};
	}
	if (!result.emailSent) {
		return {
			state: "link_only",
			level: "warning",
			message: result.error
				? __("The order was saved and a payment link was created, but the email was not sent: {0}", [
						result.error,
					])
				: __("The order was saved and a payment link was created, but the email was not sent."),
			canRetry: true,
		};
	}
	if (!result.attachmentOk) {
		return {
			state: "attachment_missing",
			level: "warning",
			message: __(
				"The pro forma email was sent with the payment link, but the pro forma PDF could not be attached. Resend it to try again.",
			),
			canRetry: true,
		};
	}
	return {
		state: "sent",
		level: "success",
		message: email
			? __("Pro forma emailed to {0} with its payment link.", [email])
			: __("Pro forma emailed to the customer with its payment link."),
		canRetry: false,
	};
}

/**
 * Asks the server to create the payment link and email the pro forma. Never throws:
 * a network or permission failure comes back as `{ ok: false, error }`.
 */
export async function sendProforma(
	salesOrder: string,
	{ resend = false }: { resend?: boolean } = {},
): Promise<ProformaResult> {
	const args: Record<string, any> = { sales_order: salesOrder };
	if (resend) {
		args.resend = 1;
	}
	try {
		const response: any = await new Promise((resolve, reject) => {
			frappe.call({
				method: SEND_PROFORMA_METHOD,
				type: "POST",
				args,
				callback: (r: any) => resolve(r),
				error: (r: any) => reject(r),
			});
		});
		return normaliseProformaResponse(response);
	} catch (failure: any) {
		const server = text(failure?.message) || text(failure?._error_message) || text(failure?.exc_type);
		return normaliseProformaResponse({
			message: { ok: false, error: server || "" },
		});
	}
}

export default { sendProforma, describeProformaResult, normaliseProformaResponse };
