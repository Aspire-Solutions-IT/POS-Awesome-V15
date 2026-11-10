/**
 * On-device queue for Yellow Ticket photos taken on the till.
 *
 * Every photo is written here first, then uploaded; it is only deleted once the
 * server confirms it has stored it. Uploads that fail (offline, server error) stay
 * queued and are retried, so a failed upload never blocks a sale.
 *
 * Kept in its own IndexedDB database rather than adding a table to
 * `posawesome_offline`, so it cannot disturb the main offline store's schema.
 */
import Dexie from "dexie/dist/dexie.mjs";

import { YT_API, postMethod } from "../posapp/utils/yellowTicketPhotos";

export interface QueuedYellowTicketPhoto {
	client_photo_ref: string;
	client_ref: string;
	pos_profile: string;
	cashier?: string;
	row_ref: string;
	item_code: string;
	item_name: string;
	qty: number;
	data_url: string;
	created_at: string;
	attempts: number;
	last_error?: string | null;
}

const photoDb = new Dexie("posawesome_yellow_ticket_photos");
photoDb.version(1).stores({
	photos: "&client_photo_ref,client_ref,created_at",
});

const RETRY_INTERVAL_MS = 60 * 1000;
// A photo the server keeps refusing (e.g. its line is no longer Yellow Ticket) is
// dropped after this many tries rather than retried forever.
const MAX_ATTEMPTS = 50;
let flushing: Promise<number> | null = null;
let timer: ReturnType<typeof setInterval> | null = null;

export async function queuePhoto(photo: Omit<QueuedYellowTicketPhoto, "attempts" | "created_at">) {
	await photoDb.table("photos").put({ ...photo, attempts: 0, created_at: new Date().toISOString() });
}

export async function pendingPhotoCount(): Promise<number> {
	return photoDb.table("photos").count();
}

function isPermanentRefusal(error: any) {
	// 4xx other than auth/rate-limit: the server looked at the photo and said no.
	return error?.status >= 400 && error?.status < 500 && ![401, 403, 408, 429].includes(error.status);
}

async function uploadOne(photo: QueuedYellowTicketPhoto) {
	await postMethod(`${YT_API}.upload_till_photo`, {
		client_ref: photo.client_ref,
		pos_profile: photo.pos_profile,
		cashier: photo.cashier,
		row_ref: photo.row_ref,
		item_code: photo.item_code,
		item_name: photo.item_name,
		qty: photo.qty,
		filename: "photo.jpg",
		content_base64: photo.data_url,
		client_photo_ref: photo.client_photo_ref,
	});
}

/** Upload everything queued, oldest first. Returns how many were uploaded. */
export function flushPhotoQueue(): Promise<number> {
	if (flushing) return flushing;
	flushing = (async () => {
		if (typeof navigator !== "undefined" && navigator.onLine === false) return 0;
		let uploaded = 0;
		const photos: QueuedYellowTicketPhoto[] = await photoDb.table("photos").orderBy("created_at").toArray();
		for (const photo of photos) {
			try {
				await uploadOne(photo);
				await photoDb.table("photos").delete(photo.client_photo_ref);
				uploaded += 1;
			} catch (error: any) {
				const attempts = (photo.attempts || 0) + 1;
				if (isPermanentRefusal(error) && attempts >= MAX_ATTEMPTS) {
					console.error("Dropping Yellow Ticket photo after repeated refusals", photo.client_photo_ref, error);
					await photoDb.table("photos").delete(photo.client_photo_ref);
					continue;
				}
				await photoDb
					.table("photos")
					.update(photo.client_photo_ref, { attempts, last_error: String(error?.message || error) });
				if (!isPermanentRefusal(error)) break; // offline or server down: try again later
			}
		}
		return uploaded;
	})().finally(() => {
		flushing = null;
	});
	return flushing;
}

/** Start retrying queued uploads in the background. Safe to call more than once. */
export function startPhotoQueueFlusher() {
	if (timer || typeof window === "undefined") return;
	timer = setInterval(() => void flushPhotoQueue().catch(() => undefined), RETRY_INTERVAL_MS);
	window.addEventListener("online", () => void flushPhotoQueue().catch(() => undefined));
	void flushPhotoQueue().catch(() => undefined);
}
