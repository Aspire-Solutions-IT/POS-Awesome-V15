/**
 * Typed DHD delivery address for an order (AP-1).
 *
 * The one place that talks to the server's `create_order_address`, which saves the typed
 * address as a reusable Shipping Address on the customer (or returns the one already there).
 * Partners and staff both use it, and only for a DHD delivery charge.
 */

const CREATE_ORDER_ADDRESS_METHOD = "posawesome.posawesome.api.order_address.create_order_address";

export const DHD_ORDER_TYPE_NAME = "DHD";
export const DEFAULT_ADDRESS_COUNTRY = "United Kingdom";

export type OrderAddressInput = {
	address_line1: string;
	address_line2?: string;
	city: string;
	county?: string;
	pincode: string;
	country: string;
	phone?: string;
	email_id?: string;
};

export type OrderAddressResult = {
	name: string;
	created: boolean;
};

export type OrderAddressRequest = {
	customer: string;
	deliveryCharge: string;
	address: OrderAddressInput;
};

/** A delivery charge row is DHD when the server named its Order Type "DHD". */
export const isDhdCharge = (row?: { order_type_name?: unknown } | null): boolean =>
	String(row?.order_type_name ?? "").trim() === DHD_ORDER_TYPE_NAME;

/** "Add Customer Address" saves an Address a partner may not create, so it is staff only. */
export const canShowAddAddressAction = (isPartner: boolean, usesStoreCollection: boolean): boolean =>
	!isPartner && !usesStoreCollection;

const stripHtml = (value: string): string => value.replace(/<[^>]+>/g, "").trim();

/** The readable reason a failed call gives: the server message, else a generic fallback. */
export function orderAddressErrorMessage(error: any, fallback = "Could not save the address."): string {
	const raw = error?._server_messages;
	if (typeof raw === "string") {
		try {
			const parsed = JSON.parse(raw);
			const first = Array.isArray(parsed) ? parsed[0] : null;
			const message = typeof first === "string" ? JSON.parse(first)?.message : first?.message;
			if (typeof message === "string" && message.trim()) {
				return stripHtml(message);
			}
		} catch {
			// fall through to the other sources
		}
	}
	for (const candidate of [error?._error_message, error?.message, error?.exception]) {
		if (typeof candidate === "string" && candidate.trim()) {
			// "frappe.exceptions.ValidationError: text" -> "text"
			return stripHtml(candidate.replace(/^[\w.]+(Error|Exception):\s*/, ""));
		}
	}
	if (error?.status === 403) {
		return "You do not have permission to save this address.";
	}
	return fallback;
}

/**
 * Turns a failed HTTP response (status + parsed JSON body, possibly empty) into the error the
 * form shows. Frappe puts the readable reason in `_server_messages`; a 403 may have no body.
 */
export function orderAddressErrorFromResponse(status: number, body: any): Record<string, unknown> {
	const data = body && typeof body === "object" ? body : {};
	const error: Record<string, unknown> = { ...data, status };
	error.message = orderAddressErrorMessage({ ...data, status }, "");
	return error;
}

const csrfToken = (): string => String((window as any).frappe?.csrf_token || "");

/**
 * Saves the address (POST) and returns its name. Rejects with the parsed error.
 *
 * Uses fetch rather than frappe.call: frappe.call opens its own error modal (duplicating the
 * inline message) and its 403 handler calls the error callback with no response body.
 */
export async function createOrderAddress(request: OrderAddressRequest): Promise<OrderAddressResult> {
	const body = new URLSearchParams();
	body.append("customer", request.customer);
	body.append("delivery_charge", request.deliveryCharge);
	body.append("address", JSON.stringify(request.address));
	const headers: Record<string, string> = {
		"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
		Accept: "application/json",
	};
	const csrf = csrfToken();
	if (csrf) {
		headers["X-Frappe-CSRF-Token"] = csrf;
	}
	let response: Response;
	try {
		response = await fetch(`/api/method/${CREATE_ORDER_ADDRESS_METHOD}`, {
			method: "POST",
			credentials: "include",
			headers,
			body: body.toString(),
		});
	} catch {
		throw { message: "Could not reach the server. Check the connection and try again." };
	}
	let data: any = null;
	try {
		data = await response.json();
	} catch {
		// non-JSON error page
	}
	if (!response.ok || data?.exc) {
		throw orderAddressErrorFromResponse(response.status, data);
	}
	const result = data?.message;
	if (!result || typeof result.name !== "string" || !result.name) {
		throw { message: "The server did not return an address." };
	}
	return { name: result.name, created: Boolean(result.created) };
}
