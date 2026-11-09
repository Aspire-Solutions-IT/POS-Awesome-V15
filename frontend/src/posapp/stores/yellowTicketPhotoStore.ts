/**
 * Yellow Ticket photos for the basket currently at checkout.
 *
 * `clientRef` identifies the basket to the server; photos taken on the till are
 * kept here (for thumbnails and counting) and in the on-device upload queue.
 * Photos taken on a phone are only known through `serverCounts`, refreshed while
 * the photo dialog is open.
 *
 * A line's count is the larger of the till photos seen here and those the server
 * already has (covers a page reload mid-checkout), plus the phone photos.
 */
import { ref } from "vue";
import { defineStore } from "pinia";

import { flushPhotoQueue, queuePhoto } from "../../offline/yellowTicketPhotoQueue";
import {
	YT_API,
	compressPhoto,
	newClientRef,
	newPhotoRef,
	postMethod,
	type YellowTicketLine,
	type YellowTicketSubmission,
} from "../utils/yellowTicketPhotos";

interface LocalPhoto {
	client_photo_ref: string;
	data_url: string;
}

interface ServerCounts {
	till: Record<string, number>;
	phone: Record<string, number>;
}

export const useYellowTicketPhotoStore = defineStore("yellowTicketPhotos", () => {
	const clientRef = ref(newClientRef());
	const photos = ref<Record<string, LocalPhoto[]>>({});
	const serverCounts = ref<ServerCounts>({ till: {}, phone: {} });
	const photosOwed = ref(false);

	const reset = () => {
		clientRef.value = newClientRef();
		photos.value = {};
		serverCounts.value = { till: {}, phone: {} };
		photosOwed.value = false;
	};

	/** Forget photos for lines no longer in the basket. */
	const keepOnly = (rowRefs: string[]) => {
		const keep = new Set(rowRefs);
		photos.value = Object.fromEntries(Object.entries(photos.value).filter(([row]) => keep.has(row)));
	};

	const localCount = (rowRef: string) => photos.value[rowRef]?.length || 0;

	const count = (rowRef: string) =>
		Math.max(localCount(rowRef), serverCounts.value.till[rowRef] || 0) + (serverCounts.value.phone[rowRef] || 0);

	const addPhoto = async (file: Blob, line: YellowTicketLine, posProfile: string, cashier?: string) => {
		const dataUrl = await compressPhoto(file);
		const photo = {
			client_photo_ref: newPhotoRef(),
			client_ref: clientRef.value,
			pos_profile: posProfile,
			cashier,
			row_ref: line.row_ref,
			item_code: line.item_code,
			item_name: line.item_name,
			qty: line.qty,
			data_url: dataUrl,
		};
		// Saved on the device before anything else, so a failed upload loses nothing.
		await queuePhoto(photo);
		photos.value = {
			...photos.value,
			[line.row_ref]: [...(photos.value[line.row_ref] || []), { client_photo_ref: photo.client_photo_ref, data_url: dataUrl }],
		};
		void flushPhotoQueue().catch(() => undefined);
	};

	const refreshServerCounts = async (posProfile: string) => {
		const result = await postMethod<ServerCounts>(`${YT_API}.get_session_counts`, {
			client_ref: clientRef.value,
			pos_profile: posProfile,
		});
		serverCounts.value = { till: result?.till || {}, phone: result?.phone || {} };
	};

	const requestPhoneLink = (posProfile: string, lines: YellowTicketLine[], cashier?: string) =>
		postMethod<{ url: string; qr: string; expires_on: string }>(`${YT_API}.create_phone_link`, {
			client_ref: clientRef.value,
			pos_profile: posProfile,
			lines,
			cashier,
		});

	const submission = (lines: YellowTicketLine[]): YellowTicketSubmission => ({
		client_ref: clientRef.value,
		lines: lines.map(({ row_ref, item_code, item_name, qty }) => ({ row_ref, item_code, item_name, qty })),
		photos_owed: photosOwed.value ? 1 : 0,
	});

	return {
		clientRef,
		photos,
		serverCounts,
		photosOwed,
		reset,
		keepOnly,
		localCount,
		count,
		addPhoto,
		refreshServerCounts,
		requestPhoneLink,
		submission,
	};
});
