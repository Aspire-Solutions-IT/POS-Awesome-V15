// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const offlineState = vi.hoisted(() => ({ offline: false, items: {} as Record<string, any> }));
const postMethod = vi.hoisted(() => vi.fn());
const queuePhoto = vi.hoisted(() => vi.fn());

vi.mock("../src/offline/index", () => ({
	isOffline: () => offlineState.offline,
	db: {
		table: () => ({
			bulkGet: async (codes: string[]) => codes.map((code) => offlineState.items[code]),
		}),
	},
}));

vi.mock("../src/offline/yellowTicketPhotoQueue", () => ({
	queuePhoto,
	flushPhotoQueue: vi.fn(async () => 0),
	startPhotoQueueFlusher: vi.fn(),
}));

vi.mock("../src/posapp/utils/yellowTicketPhotos", async (importOriginal) => {
	const actual: any = await importOriginal();
	return { ...actual, postMethod, compressPhoto: vi.fn(async () => "data:image/jpeg;base64,AAAA") };
});

import { useYellowTicketPhotoGate } from "../src/posapp/composables/pos/payments/useYellowTicketPhotoGate";
import { useYellowTicketPhotoStore } from "../src/posapp/stores/yellowTicketPhotoStore";
import { invoiceLines, isYellowTicketLine, minimumPhotosForItem } from "../src/posapp/utils/yellowTicketPhotos";

const profile = { name: "Till 1", posa_require_yellow_ticket_photos: 1 };
const doc = {
	items: [
		{ item_code: "NS-SOFA", item_name: "NS Sofa", qty: 1, posa_row_id: "r-ns" },
		{ item_code: "CHAIR", item_name: "Chair", qty: 2, posa_row_id: "r-chair", item_group: "Chairs" },
		{ item_code: "YT-TABLE", item_name: "Table", qty: 1, posa_row_id: "r-yt" },
	],
};

function serverSays(rowRefs: string[], counts = { till: {}, phone: {} }, enabled = true) {
	postMethod.mockImplementation(async (method: string) => {
		if (method.endsWith("get_requirements")) {
			return { enabled, min_photos: 3, max_photos: 10, row_refs: rowRefs };
		}
		if (method.endsWith("get_session_counts")) return counts;
		throw new Error(`unexpected ${method}`);
	});
}

describe("Yellow Ticket photo rule", () => {
	it.each(["NS-ACCESSORY-AA", "NS-ACCESSORY-AB", "NS-ACCESSORY-AD", " ns-accessory-zz "])(
		"requires one photo for accessory prefix %s",
		(code) => {
			expect(minimumPhotosForItem(code)).toBe(1);
			expect(minimumPhotosForItem(code, 4)).toBe(1);
		},
	);

	it("keeps the normal minimum for other items and excludes Stainguard accessories", () => {
		for (const code of ["NS-SOFA", "NS-ACCESS", "OTHER-NS-ACCESSORY-AA", "YT-TABLE"]) {
			expect(minimumPhotosForItem(code)).toBe(3);
			expect(minimumPhotosForItem(code, 4)).toBe(4);
		}
		expect(isYellowTicketLine("NS-ACCESSORY-AA", "Yellow Ticket", 1)).toBe(false);
	});

	it("matches the Yellow Ticket group or an NS item code", () => {
		expect(isYellowTicketLine("NS-1", "Sofas")).toBe(true);
		expect(isYellowTicketLine("abc", " Yellow Ticket ")).toBe(true);
		expect(isYellowTicketLine("SOFA", "Sofas")).toBe(false);
		expect(isYellowTicketLine("", "Yellow Ticket")).toBe(false);
		expect(isYellowTicketLine("NS-COVER", "Yellow Ticket", 1)).toBe(false);
		expect(isYellowTicketLine("NS-COVER", "Yellow Ticket", "0")).toBe(true);
	});

	it("skips free items and lines without a till line ID", () => {
		const lines = invoiceLines({
			items: [
				{ item_code: "A", posa_row_id: "1", qty: 1 },
				{ item_code: "B", qty: 1 },
				{ item_code: "C", posa_row_id: "3", is_free_item: 1 },
				{ item_code: "NS-COVER", posa_row_id: "4", is_staingard_item: "1" },
			],
		});
		expect(lines.map((line) => line.row_ref)).toEqual(["1"]);
	});
});

describe("useYellowTicketPhotoGate", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		localStorage.clear();
		offlineState.offline = false;
		offlineState.items = {};
		postMethod.mockReset();
		queuePhoto.mockReset();
	});

	it.each([false, true])("uses one photo per accessory but three for other NS items (offline=%s)", async (offline) => {
		offlineState.offline = offline;
		if (offline) {
			localStorage.setItem("posa_yt_photo_config_Till 1", JSON.stringify({ enabled: true, min_photos: 3, max_photos: 10 }));
		} else {
			serverSays(["accessory-aa", "accessory-ad", "r-ns"]);
		}
		const basket = { items: [
			{ item_code: "NS-ACCESSORY-AA", posa_row_id: "accessory-aa", qty: 2 },
			{ item_code: "NS-ACCESSORY-AD", posa_row_id: "accessory-ad", qty: 1 },
			doc.items[0],
		] };
		const gate = useYellowTicketPhotoGate();
		const store = useYellowTicketPhotoStore();
		const pending = gate.ensureYellowTicketPhotos(profile, basket, "Invoice");
		await vi.waitFor(() => expect(gate.dialogOpen.value).toBe(true));
		expect(gate.lines.value.map(gate.minimumPhotos)).toEqual([1, 1, 3]);
		for (const line of gate.lines.value) {
			await store.addPhoto(new Blob(["photo"]), line, "Till 1");
		}
		expect(gate.isComplete()).toBe(false);
		for (let photoIndex = 0; photoIndex < 2; photoIndex++) {
			await store.addPhoto(new Blob(["photo"]), gate.lines.value[2], "Till 1");
		}
		expect(gate.isComplete()).toBe(true);
		gate.continueSale();
		expect(await pending).toMatchObject({ photos_owed: 0 });
	});

	it("uses authoritative per-line minimums from the server", async () => {
		postMethod.mockImplementation(async (method: string) => method.endsWith("get_requirements")
			? { enabled: true, min_photos: 3, max_photos: 10, row_refs: ["r-ns"], min_photos_by_row: { "r-ns": 2 } }
			: { till: {}, phone: {} });
		const gate = useYellowTicketPhotoGate();
		const pending = gate.ensureYellowTicketPhotos(profile, doc, "Invoice");
		await vi.waitFor(() => expect(gate.dialogOpen.value).toBe(true));
		expect(gate.minimumPhotos(gate.lines.value[0])).toBe(2);
		gate.cancel();
		expect(await pending).toBe(false);
	});

	it("does nothing unless the POS Profile opts in", async () => {
		const gate = useYellowTicketPhotoGate();
		expect(await gate.ensureYellowTicketPhotos({ name: "Till 1" }, doc, "Invoice")).toBeUndefined();
		expect(postMethod).not.toHaveBeenCalled();
	});

	it("does nothing for returns, quotations, or when the site switch is off", async () => {
		const gate = useYellowTicketPhotoGate();
		expect(await gate.ensureYellowTicketPhotos(profile, { ...doc, is_return: 1 }, "Invoice")).toBeUndefined();
		expect(await gate.ensureYellowTicketPhotos(profile, doc, "Quotation")).toBeUndefined();
		serverSays([], undefined, false);
		expect(await gate.ensureYellowTicketPhotos(profile, doc, "Invoice")).toBeUndefined();
	});

	it("opens the dialog for the lines the server names and continues once photos are in", async () => {
		serverSays(["r-ns", "r-yt"]);
		const gate = useYellowTicketPhotoGate();
		const store = useYellowTicketPhotoStore();
		const pending = gate.ensureYellowTicketPhotos(profile, doc, "Order", "cashier@example.com");
		await vi.waitFor(() => expect(gate.dialogOpen.value).toBe(true));
		expect(gate.lines.value.map((line) => line.row_ref)).toEqual(["r-ns", "r-yt"]);
		expect(gate.isComplete()).toBe(false);

		for (const line of gate.lines.value) {
			for (let i = 0; i < 3; i += 1) {
				await store.addPhoto(new Blob(["x"]), line, "Till 1", "cashier@example.com");
			}
		}
		expect(queuePhoto).toHaveBeenCalledTimes(6);
		expect(queuePhoto.mock.calls[0][0]).toMatchObject({ cashier: "cashier@example.com", row_ref: "r-ns" });
		expect(gate.isComplete()).toBe(true);

		gate.continueSale();
		const result = await pending;
		expect(result).toMatchObject({ client_ref: store.clientRef, photos_owed: 0 });
		expect((result as any).lines.map((line: any) => line.row_ref)).toEqual(["r-ns", "r-yt"]);
		expect(gate.dialogOpen.value).toBe(false);
	});

	it("counts phone photos and skips the dialog when the basket is already complete", async () => {
		serverSays(["r-ns"], { till: {}, phone: { "r-ns": 3 } });
		const gate = useYellowTicketPhotoGate();
		const result = await gate.ensureYellowTicketPhotos(profile, doc, "Invoice");
		expect(result).toMatchObject({ photos_owed: 0 });
		expect(gate.dialogOpen.value).toBe(false);
	});

	it("does not double count till photos the server already has", async () => {
		serverSays(["r-ns"], { till: { "r-ns": 2 }, phone: { "r-ns": 0 } });
		const gate = useYellowTicketPhotoGate();
		const store = useYellowTicketPhotoStore();
		const pending = gate.ensureYellowTicketPhotos(profile, doc, "Invoice");
		await vi.waitFor(() => expect(gate.dialogOpen.value).toBe(true));
		await store.addPhoto(new Blob(["x"]), gate.lines.value[0], "Till 1");
		await store.addPhoto(new Blob(["x"]), gate.lines.value[0], "Till 1");
		expect(store.count("r-ns")).toBe(2);
		gate.cancel();
		expect(await pending).toBe(false);
	});

	it("offline: uses the cached switch and the NS / item group rule, and allows photos owed", async () => {
		serverSays(["r-ns"]);
		const gate = useYellowTicketPhotoGate();
		// One online check caches the site-wide setting for this till.
		const first = gate.ensureYellowTicketPhotos(profile, doc, "Invoice");
		await vi.waitFor(() => expect(gate.dialogOpen.value).toBe(true));
		gate.cancel();
		await first;

		offlineState.offline = true;
		offlineState.items = { "YT-TABLE": { item_code: "YT-TABLE", item_group: "Yellow Ticket" } };
		postMethod.mockReset();
		const pending = gate.ensureYellowTicketPhotos(profile, doc, "Invoice");
		await vi.waitFor(() => expect(gate.dialogOpen.value).toBe(true));
		expect(postMethod).not.toHaveBeenCalled();
		expect(gate.lines.value.map((line) => line.row_ref)).toEqual(["r-ns", "r-yt"]);

		gate.markPhotosOwed();
		expect(await pending).toMatchObject({ photos_owed: 1 });
	});

	it("offline with no cached setting never blocks the sale", async () => {
		offlineState.offline = true;
		const gate = useYellowTicketPhotoGate();
		expect(await gate.ensureYellowTicketPhotos(profile, doc, "Invoice")).toBeUndefined();
	});

	it("offline: excludes Stainguard flagged in the cached item master", async () => {
		localStorage.setItem("posa_yt_photo_config_Till 1", JSON.stringify({ enabled: true, min_photos: 3, max_photos: 10 }));
		offlineState.offline = true;
		offlineState.items = {
			"NS-SOFA": { item_code: "NS-SOFA", item_group: "Yellow Ticket", is_staingard_item: 1 },
		};
		const gate = useYellowTicketPhotoGate();
		expect(await gate.ensureYellowTicketPhotos(profile, { items: [doc.items[0]] }, "Invoice")).toBeUndefined();
		expect(gate.dialogOpen.value).toBe(false);
		expect(postMethod).not.toHaveBeenCalled();
	});

	it("does not ask again at submission after photos were completed before payment", async () => {
		serverSays(["r-ns"]);
		const gate = useYellowTicketPhotoGate();
		const store = useYellowTicketPhotoStore();
		const pending = gate.ensureYellowTicketPhotos(profile, doc, "Invoice");
		await vi.waitFor(() => expect(gate.dialogOpen.value).toBe(true));
		for (let photoIndex = 0; photoIndex < 3; photoIndex++) {
			await store.addPhoto(new Blob(["x"]), gate.lines.value[0], "Till 1");
		}
		gate.continueSale();
		const beforePayment = await pending;
		const atSubmission = await gate.ensureYellowTicketPhotos(profile, doc, "Invoice");
		expect(atSubmission).toEqual(beforePayment);
		expect(gate.dialogOpen.value).toBe(false);
	});

	it("starts a new basket after the sale", async () => {
		const store = useYellowTicketPhotoStore();
		const before = store.clientRef;
		useYellowTicketPhotoGate().completeSale();
		expect(store.clientRef).not.toBe(before);
		expect(store.photosOwed).toBe(false);
	});
});
