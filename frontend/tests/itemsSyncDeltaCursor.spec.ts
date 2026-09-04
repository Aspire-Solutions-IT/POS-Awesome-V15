import { beforeEach, describe, expect, it, vi } from "vitest";

const offlineMocks = vi.hoisted(() => ({
	saveItemsBulk: vi.fn(async () => {}),
	clearStoredItems: vi.fn(async () => {}),
	setItemsLastSync: vi.fn(),
	getItemsLastSync: vi.fn(),
	saveItemDetailsCache: vi.fn(),
	saveItemUOMs: vi.fn(),
	saveItemGroups: vi.fn(),
	getCachedItemGroups: vi.fn(() => null),
	refreshBootstrapSnapshotFromCacheState: vi.fn(),
}));

vi.mock("../src/offline/index", () => offlineMocks);

vi.mock("../src/posapp/services/itemService", () => ({
	default: {
		getItems: vi.fn(async () => []),
		getItemGroups: vi.fn(async () => []),
		getItemsCount: vi.fn(async () => 0),
	},
}));

import { useItemsSync } from "../src/posapp/composables/pos/items/store/useItemsSync";

const profile = { name: "POS-1", warehouse: "Main WH" } as any;

const callRefresh = async (deltaRows: any[]) => {
	const { refreshModifiedItems } = useItemsSync();
	(globalThis as any).frappe = {
		call: vi.fn(async () => ({ message: deltaRows })),
	};
	return refreshModifiedItems(
		profile,
		"Retail",
		null,
		"scope",
		() => {},
		new Map(),
	);
};

describe("useItemsSync delta cursor", () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it("does not rewind the cursor when the delta rows carry older Item.modified stamps", async () => {
		// The delta is driven by Bin / Item Price changes, so the Item rows it returns
		// routinely have a much older `modified` than the cursor itself. Writing that back
		// would make every later poll return the same delta forever.
		offlineMocks.getItemsLastSync.mockReturnValue("2026-08-20 09:00:00.000000");

		await callRefresh([
			{ item_code: "ITEM-1", modified: "2024-01-05 11:22:33.000000" },
		]);

		expect(offlineMocks.setItemsLastSync).not.toHaveBeenCalled();
	});

	it("still advances the cursor when the delta rows are genuinely newer", async () => {
		offlineMocks.getItemsLastSync.mockReturnValue("2026-08-20 09:00:00.000000");

		await callRefresh([
			{ item_code: "ITEM-1", modified: "2026-08-20 09:30:00.000000" },
		]);

		expect(offlineMocks.setItemsLastSync).toHaveBeenCalledWith(
			"2026-08-20 09:30:00.000000",
		);
	});
});
