import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const itemServiceMocks = vi.hoisted(() => ({
	getItems: vi.fn(),
}));

const offlineMocks = vi.hoisted(() => ({
	refreshBootstrapSnapshotFromCacheState: vi.fn(),
	getStoredItemsCountByScope: vi.fn(async () => 0),
	getAllStoredItems: vi.fn(async () => []),
	getCachedPriceListItems: vi.fn(async () => null),
}));

const itemsSyncMocks = vi.hoisted(() => ({
	primeItemDetailsCache: vi.fn(),
	backgroundSyncItems: vi.fn(async () => []),
	refreshModifiedItems: vi.fn(),
}));

vi.mock("../src/posapp/services/itemService", () => ({
	default: {
		getItems: itemServiceMocks.getItems,
		getItemGroups: vi.fn(async () => []),
		getItemsFromBarcode: vi.fn(async () => null),
		getItemsCount: vi.fn(async () => 1),
	},
}));

vi.mock("../src/offline/index", () => ({
	refreshBootstrapSnapshotFromCacheState:
		offlineMocks.refreshBootstrapSnapshotFromCacheState,
	getStoredItemsCountByScope: offlineMocks.getStoredItemsCountByScope,
	getAllStoredItems: offlineMocks.getAllStoredItems,
	getCachedPriceListItems: offlineMocks.getCachedPriceListItems,
}));

vi.mock("../src/posapp/composables/pos/items/store/useItemsCache", () => ({
	useItemsCache: () => ({
		cache: {
			value: {
				memory: {
					searchResults: new Map(),
					priceListData: new Map(),
					itemDetails: new Map(),
				},
			},
		},
		cacheHealth: { value: { items: "healthy" } },
		assessCacheHealth: vi.fn(async () => {}),
		clearAllCaches: vi.fn(async () => {}),
		clearSearchCache: vi.fn(),
		getCachedItems: vi.fn(async () => null),
		cacheItems: vi.fn(async () => {}),
		getCachedSearchResult: vi.fn(() => null),
		setCachedSearchResult: vi.fn(),
		getCachedPriceList: vi.fn(() => null),
		setCachedPriceList: vi.fn(),
		generateCacheKey: vi.fn(
			(searchValue = "", group = "ALL", priceList = "", scope = "") =>
				`${scope}:${priceList}:${group}:${searchValue}`,
		),
	}),
}));

vi.mock("../src/posapp/composables/pos/items/store/useItemsSearch", () => ({
	useItemsSearch: () => {
		const itemsMap = { value: new Map<string, any>() };
		const barcodeIndex = { value: new Map<string, any>() };

		return {
			itemsMap,
			barcodeIndex,
			updateIndexes: (items: any[] = []) => {
				items.forEach((item) => {
					if (item?.item_code) {
						itemsMap.value.set(item.item_code, item);
					}
				});
			},
			resetIndexes: () => {
				itemsMap.value = new Map();
				barcodeIndex.value = new Map();
			},
			// Behaves like the real search: only matches what is in the array it is given.
			performLocalSearch: (term: string, items: any[] = []) =>
				items.filter((item) =>
					String(item?.item_code || "")
						.toLowerCase()
						.includes(String(term || "").toLowerCase()),
				),
			filterItemsByGroup: (items: any[], group: string) =>
				group && group !== "ALL"
					? items.filter((item) => item?.item_group === group)
					: items,
			getItemByCode: (code: string) => itemsMap.value.get(code),
			getItemByBarcode: (barcode: string) => barcodeIndex.value.get(barcode),
		};
	},
}));

vi.mock("../src/posapp/composables/pos/items/store/useItemsSync", () => ({
	useItemsSync: () => ({
		isLoading: { value: false },
		isBackgroundLoading: { value: false },
		loadProgress: { value: 0 },
		requestToken: { value: 0 },
		abortControllers: { value: new Map<string, AbortController>() },
		backgroundSyncState: { value: { running: false, token: 0 } },
		itemGroups: { value: ["ALL"] },
		loadItemGroups: vi.fn(async () => {}),
		persistItemsToStorage: vi.fn(async () => {}),
		primeItemDetailsCache: itemsSyncMocks.primeItemDetailsCache,
		cancelBackgroundSync: vi.fn(),
		refreshModifiedItems: itemsSyncMocks.refreshModifiedItems,
		backgroundSyncItems: itemsSyncMocks.backgroundSyncItems,
	}),
}));

vi.mock("../src/posapp/composables/pos/items/store/useItemsPagination", () => ({
	useItemsPagination: () => ({
		cachedPagination: {
			value: {
				enabled: false,
				offset: 0,
				total: 0,
				loading: false,
				pageSize: 50,
				search: "",
				group: "ALL",
			},
		},
		DEFAULT_PAGE_SIZE: 50,
		LARGE_CATALOG_THRESHOLD: 500,
		resolvePageSize: vi.fn(() => 50),
		resolveLimitSearchSize: vi.fn(() => 50),
		resetCachedPagination: vi.fn(),
		updateCachedPaginationFromStorage: vi.fn(async () => {}),
	}),
}));

vi.mock("../src/posapp/composables/pos/items/store/useItemsMetrics", () => ({
	useItemsMetrics: () => ({
		performanceMetrics: {
			value: {
				totalRequests: 0,
				cachedRequests: 0,
				searchHits: 0,
				searchMisses: 0,
			},
		},
		updatePerformanceMetrics: vi.fn(),
		getEstimatedMemoryUsage: vi.fn(() => 0),
	}),
}));

import { useItemsStore } from "../src/posapp/stores/itemsStore";

const profile = {
	name: "POS-1",
	warehouse: "Main WH",
	selling_price_list: "Retail",
	currency: "GBP",
	item_groups: [],
} as any;

describe("itemsStore background sync vs. active search", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		setActivePinia(createPinia());
		itemServiceMocks.getItems.mockResolvedValue([
			{ item_code: "IN-MEMORY-1", item_name: "Loaded page item", rate: 10 },
		]);
	});

	it("keeps search results that live outside the in-memory page when a delta arrives", async () => {
		const store = useItemsStore();
		await store.initialize(profile);

		// Simulates the IndexedDB / server search path: the visible results are NOT all
		// present in `items`, which only holds the currently loaded page.
		const searchOnlyRow = { item_code: "WIDGET-9", item_name: "Widget", rate: 50 };
		store.searchTerm = "widget";
		store.filteredItems = [searchOnlyRow as any];

		itemsSyncMocks.refreshModifiedItems.mockImplementation(
			async (
				_profile: any,
				_priceList: any,
				_customer: any,
				_scope: any,
				updateItemsInPlace: (_items: any[]) => void,
			) => {
				updateItemsInPlace([{ item_code: "IN-MEMORY-1", rate: 11 }]);
				return { size: 1, count: 1, items: [] };
			},
		);

		await store.refreshModifiedItems();

		expect(store.filteredItems).toHaveLength(1);
		expect(store.filteredItems[0]?.item_code).toBe("WIDGET-9");
	});

	it("patches changed rows that are visible in the current search results", async () => {
		const store = useItemsStore();
		await store.initialize(profile);

		const visibleRow = { item_code: "IN-MEMORY-1", item_name: "Loaded page item", rate: 10 };
		store.searchTerm = "in-memory";
		store.filteredItems = [visibleRow as any];

		itemsSyncMocks.refreshModifiedItems.mockImplementation(
			async (
				_profile: any,
				_priceList: any,
				_customer: any,
				_scope: any,
				updateItemsInPlace: (_items: any[]) => void,
			) => {
				updateItemsInPlace([{ item_code: "IN-MEMORY-1", rate: 11 }]);
				return { size: 1, count: 1, items: [] };
			},
		);

		await store.refreshModifiedItems();

		expect(store.filteredItems).toHaveLength(1);
		expect(store.filteredItems[0]?.rate).toBe(11);
	});

	it("still rebuilds the visible list from the catalogue when no search is active", async () => {
		const store = useItemsStore();
		await store.initialize(profile);

		store.searchTerm = "";

		itemsSyncMocks.refreshModifiedItems.mockImplementation(
			async (
				_profile: any,
				_priceList: any,
				_customer: any,
				_scope: any,
				updateItemsInPlace: (_items: any[]) => void,
			) => {
				updateItemsInPlace([
					{ item_code: "NEW-ITEM", item_name: "Newly synced", rate: 5 },
				]);
				return { size: 1, count: 1, items: [] };
			},
		);

		await store.refreshModifiedItems();

		expect(
			store.filteredItems.map((item: any) => item.item_code),
		).toContain("NEW-ITEM");
	});
});
