import { describe, expect, it } from "vitest";

import {
	canSplitDelivery,
	hasLegacyChargeRows,
	isShipCompleteCharge,
	markUnverifiedCachedCharges,
} from "../src/posapp/composables/pos/invoice/shipComplete";

describe("ship-complete rule", () => {
	it("recognises the flag in the shapes the server and cache use", () => {
		for (const flag of [1, "1", true]) {
			expect(isShipCompleteCharge({ ship_complete: flag })).toBe(true);
		}
		for (const flag of [0, "0", false, null, undefined]) {
			expect(isShipCompleteCharge({ ship_complete: flag })).toBe(false);
		}
		expect(isShipCompleteCharge(null)).toBe(false);
	});

	it("never offers a split on a ship-complete charge or a collection charge", () => {
		expect(canSplitDelivery({ ship_complete: 1 }, false)).toBe(false);
		expect(canSplitDelivery({ ship_complete: 0 }, true)).toBe(false);
		expect(canSplitDelivery({ ship_complete: 0 }, false)).toBe(true);
		expect(canSplitDelivery(null, false)).toBe(true);
	});

	it("treats a cached row with no ship_complete as stale and never offers a split on it", () => {
		const cached = [{ name: "Legacy" }, { name: "Current", ship_complete: 0 }];
		expect(hasLegacyChargeRows(cached)).toBe(true);
		expect(hasLegacyChargeRows([{ name: "Current", ship_complete: 0 }])).toBe(false);
		const marked = markUnverifiedCachedCharges(cached);
		expect(canSplitDelivery(marked[0], false)).toBe(false);
		expect(canSplitDelivery(marked[1], false)).toBe(true);
		expect(markUnverifiedCachedCharges(undefined)).toEqual([]);
	});
});
