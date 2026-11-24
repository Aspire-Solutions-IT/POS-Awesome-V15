import {
	initPromise,
	clearStoredItems,
	clearPriceListCache,
	clearItemDetailsCache,
	clearCustomerStorage,
	clearCustomerBalanceCache,
	clearLocalStockCache,
} from "../../offline/index";

/**
 * A partner's browser must start from nothing: whatever a previous (staff) session left
 * in the item, price, customer and stock caches belongs to a different scope and carries
 * prices and cost data a partner must not see. Read caches only; the queue of offline
 * sales and customers waiting to upload is deliberately left alone.
 */
export async function purgeBrowserCachesForPartner() {
	await initPromise;

	const steps: Array<() => unknown> = [
		() => clearStoredItems(),
		() => clearPriceListCache(),
		() => clearItemDetailsCache(),
		() => clearCustomerStorage(),
		() => clearCustomerBalanceCache(),
		() => clearLocalStockCache(),
	];
	for (const step of steps) {
		try {
			await step();
		} catch (error) {
			console.error("Failed to clear a cache for partner mode", error);
		}
	}
}
