/**
 * Yellow Ticket photo helpers shared by the checkout gate, the photo store and the
 * offline photo queue.
 *
 * The server (customer_due_dates.yellow_ticket_photos) is authoritative about which
 * lines need photos; `isYellowTicketLine` is only the offline fallback and uses the
 * same rule: the "Yellow Ticket" item group, or an item code starting with NS,
 * excluding Stainguard cover items.
 */

import { isStainguardItem } from "./stainguard";

type AnyRecord = Record<string, any>;

export const YT_API = "customer_due_dates.yellow_ticket_photos.api";
export const YT_REQUIREMENTS_METHOD = "posawesome.posawesome.api.yellow_ticket_photos.get_requirements";
const MAX_EDGE = 1600;
const JPEG_QUALITY = 0.8;
const CONFIG_STORAGE_PREFIX = "posa_yt_photo_config_";

export interface YellowTicketLine {
	row_ref: string;
	item_code: string;
	item_name: string;
	qty: number;
	min_photos?: number;
}

export interface YellowTicketConfig {
	enabled: boolean;
	min_photos: number;
	max_photos: number;
}

export interface YellowTicketSubmission {
	client_ref: string;
	lines: YellowTicketLine[];
	photos_owed: 0 | 1;
}

export function minimumPhotosForItem(itemCode: unknown, standardMinimum = 3): number {
	return String(itemCode || "").trim().toUpperCase().startsWith("NS-ACCESSORY") ? 1 : standardMinimum;
}

export function isYellowTicketLine(itemCode: unknown, itemGroup: unknown, stainguardFlag?: unknown): boolean {
	const code = String(itemCode || "").trim().toLowerCase();
	const group = String(itemGroup || "").trim().toLowerCase();
	return (
		!isStainguardItem({ is_staingard_item: stainguardFlag }) && Boolean(code) &&
		(group === "yellow ticket" || code.startsWith("ns"))
	);
}

export function invoiceLines(invoiceDoc: AnyRecord | null | undefined): YellowTicketLine[] {
	const items = Array.isArray(invoiceDoc?.items) ? invoiceDoc.items : [];
	return items
		.filter((item: AnyRecord) =>
			item?.item_code && item?.posa_row_id && !item?.is_free_item && !isStainguardItem(item),
		)
		.map((item: AnyRecord) => ({
			row_ref: String(item.posa_row_id),
			item_code: String(item.item_code),
			item_name: String(item.item_name || item.item_code),
			qty: Number(item.qty) || 0,
			item_group: item.item_group,
		}));
}

export function newClientRef(): string {
	const random =
		typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
			? crypto.randomUUID().replace(/-/g, "")
			: `${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
	return `ytb-${Date.now()}-${random.slice(0, 16)}`;
}

export function newPhotoRef(): string {
	return newClientRef().replace(/^ytb-/, "ytp-");
}

export function cacheConfig(posProfile: string, config: YellowTicketConfig) {
	try {
		localStorage.setItem(CONFIG_STORAGE_PREFIX + posProfile, JSON.stringify(config));
	} catch {
		/* storage full or unavailable: offline tills fall back to "not required" */
	}
}

export function cachedConfig(posProfile: string): YellowTicketConfig | null {
	try {
		const raw = localStorage.getItem(CONFIG_STORAGE_PREFIX + posProfile);
		return raw ? (JSON.parse(raw) as YellowTicketConfig) : null;
	} catch {
		return null;
	}
}

/** Shrink to at most 1600px on the long side, as JPEG, and return a data URL. */
export function compressPhoto(file: Blob): Promise<string> {
	return new Promise((resolve, reject) => {
		const url = URL.createObjectURL(file);
		const img = new Image();
		img.onload = () => {
			const scale = Math.min(1, MAX_EDGE / Math.max(img.width, img.height));
			const canvas = document.createElement("canvas");
			canvas.width = Math.max(1, Math.round(img.width * scale));
			canvas.height = Math.max(1, Math.round(img.height * scale));
			const context = canvas.getContext("2d");
			if (!context) {
				URL.revokeObjectURL(url);
				reject(new Error("Canvas unavailable"));
				return;
			}
			context.drawImage(img, 0, 0, canvas.width, canvas.height);
			URL.revokeObjectURL(url);
			resolve(canvas.toDataURL("image/jpeg", JPEG_QUALITY));
		};
		img.onerror = () => {
			URL.revokeObjectURL(url);
			reject(new Error("Unreadable image"));
		};
		img.src = url;
	});
}

/**
 * POST to a whitelisted method without frappe.call's error dialogs: background
 * photo uploads must fail quietly and retry later.
 */
export async function postMethod<T = any>(method: string, args: AnyRecord): Promise<T> {
	const body = new URLSearchParams();
	Object.entries(args).forEach(([key, value]) => {
		if (value === undefined || value === null) return;
		body.append(key, typeof value === "object" ? JSON.stringify(value) : String(value));
	});
	const headers: Record<string, string> = {
		"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
		Accept: "application/json",
	};
	const csrf = (window as any).frappe?.csrf_token;
	if (csrf) headers["X-Frappe-CSRF-Token"] = csrf;
	const response = await fetch(`/api/method/${method}`, {
		method: "POST",
		credentials: "include",
		headers,
		body: body.toString(),
	});
	let data: AnyRecord = {};
	try {
		data = await response.json();
	} catch {
		/* non-JSON error page */
	}
	if (!response.ok || data.exc) {
		const error: any = new Error(serverMessage(data) || `Request failed (${response.status})`);
		error.status = response.status;
		throw error;
	}
	return data.message as T;
}

function serverMessage(data: AnyRecord): string {
	try {
		if (data?._server_messages) {
			const first = JSON.parse(JSON.parse(data._server_messages)[0]);
			return String(first.message || "");
		}
	} catch {
		/* ignore */
	}
	return String(data?.exception || "");
}
