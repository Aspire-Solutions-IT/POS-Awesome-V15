// @vitest-environment jsdom

import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it, vi } from "vitest";

const postMethod = vi.hoisted(() => vi.fn());

vi.mock("../src/posapp/utils/yellowTicketPhotos", async (importOriginal) => {
	const actual: any = await importOriginal();
	return { ...actual, postMethod };
});

import { flushPhotoQueue, pendingPhotoCount, queuePhoto } from "../src/offline/yellowTicketPhotoQueue";

function photo(ref: string) {
	return {
		client_photo_ref: ref,
		client_ref: "ytb-basket-1",
		pos_profile: "Till 1",
		row_ref: "r1",
		item_code: "NS-1",
		item_name: "NS 1",
		qty: 1,
		data_url: "data:image/jpeg;base64,AAAA",
	};
}

describe("Yellow Ticket photo queue", () => {
	beforeEach(async () => {
		postMethod.mockReset();
		postMethod.mockResolvedValue({ photo: "YTP-1" });
		await flushPhotoQueue(); // drain anything a previous test left
		postMethod.mockReset();
	});

	it("removes a photo from the device only after the server stores it", async () => {
		await queuePhoto(photo("p1"));
		await queuePhoto(photo("p2"));
		postMethod.mockResolvedValue({ photo: "YTP-1" });

		expect(await flushPhotoQueue()).toBe(2);
		expect(await pendingPhotoCount()).toBe(0);
		expect(postMethod.mock.calls[0][1]).toMatchObject({
			client_ref: "ytb-basket-1",
			client_photo_ref: "p1",
			content_base64: "data:image/jpeg;base64,AAAA",
		});
	});

	it("keeps photos and stops when the server can't be reached", async () => {
		await queuePhoto(photo("p3"));
		await queuePhoto(photo("p4"));
		postMethod.mockRejectedValue(Object.assign(new Error("Failed to fetch"), { status: undefined }));

		expect(await flushPhotoQueue()).toBe(0);
		expect(postMethod).toHaveBeenCalledTimes(1);
		expect(await pendingPhotoCount()).toBe(2);

		postMethod.mockReset();
		postMethod.mockResolvedValue({ photo: "YTP-2" });
		expect(await flushPhotoQueue()).toBe(2);
		expect(await pendingPhotoCount()).toBe(0);
	});

	it("moves past a photo the server refuses without losing it straight away", async () => {
		await queuePhoto(photo("p5"));
		await queuePhoto(photo("p6"));
		postMethod
			.mockRejectedValueOnce(Object.assign(new Error("not a Yellow Ticket line"), { status: 417 }))
			.mockResolvedValueOnce({ photo: "YTP-3" });

		expect(await flushPhotoQueue()).toBe(1);
		expect(await pendingPhotoCount()).toBe(1);
	});
});
