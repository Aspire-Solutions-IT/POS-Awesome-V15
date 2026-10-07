import { beforeEach, describe, expect, it, vi } from "vitest";

import {
	applySupplyTypes,
	buildSuggestedSplitGroups,
	cartSupplySignature,
	clearSupplyTypes,
	hasCompleteSupplyTypes,
	storedSupplyByRowId,
	supplyByRowId,
} from "../src/posapp/utils/suggestedSplitGroups";

const cart = () => [
	{ posa_row_id: "r1", item_code: "SOFA", qty: 1, uom: "Nos" },
	{ posa_row_id: "r2", item_code: "TABLE", qty: 2, uom: "Nos" },
	{ posa_row_id: "r3", item_code: "LAMP", qty: 1, uom: "Nos" },
	{ posa_row_id: "r4", item_code: "RUG", qty: 1, uom: "Nos" },
];

describe("suggestedSplitGroups", () => {
	beforeEach(() => {
		vi.stubGlobal("__", (value: string) => value);
	});

	it("changes the signature when a line is added, removed or its qty changes", () => {
		const items = cart();
		const base = cartSupplySignature(items);

		expect(cartSupplySignature(cart())).toBe(base);
		expect(cartSupplySignature([...items, { posa_row_id: "r5", item_code: "X", qty: 1 }])).not.toBe(base);
		expect(cartSupplySignature(items.slice(1))).not.toBe(base);
		expect(cartSupplySignature(items.map((i) => (i.posa_row_id === "r2" ? { ...i, qty: 3 } : i)))).not.toBe(
			base,
		);
	});

	it("ignores supply types and rates in the signature", () => {
		const items = cart();
		const base = cartSupplySignature(items);
		applySupplyTypes(items, { r1: "In Stock" });
		(items[0] as any).rate = 99;

		expect(cartSupplySignature(items)).toBe(base);
	});

	it("takes the slowest supply when a cart row expands into several lines", () => {
		expect(
			supplyByRowId([
				{ posa_row_id: "r1", source: "In Stock" },
				{ posa_row_id: "r1", source: "Back Order" },
				{ posa_row_id: "r1", source: "On Order" },
				{ posa_row_id: "r2", source: "On Order" },
				{ posa_row_id: "r2", source: "In Stock" },
				{ posa_row_id: "", source: "In Stock" },
			]),
		).toEqual({ r1: "Back Order", r2: "On Order" });
	});

	it("stores, detects and clears supply types on cart rows", () => {
		const items = cart();
		const supplies = { r1: "In Stock", r2: "On Order", r3: "Back Order" };
		applySupplyTypes(items, supplies);
		expect(hasCompleteSupplyTypes(items)).toBe(false);

		applySupplyTypes(items, { ...supplies, r4: "In Stock" });
		expect(hasCompleteSupplyTypes(items)).toBe(true);
		expect(storedSupplyByRowId(items)).toEqual({ ...supplies, r4: "In Stock" });

		clearSupplyTypes(items);
		expect(items.some((item) => "posa_supply_type" in item)).toBe(false);
		expect(hasCompleteSupplyTypes(items)).toBe(false);
	});

	it("builds one group per supply type, earliest supply first, keeping the default group", () => {
		const groups = buildSuggestedSplitGroups(
			cart(),
{ r1: "Back Order", r2: "In Stock", r3: "On Order", r4: "In Stock" },
			"default",
		);

		expect(groups).toEqual([
			{ group_id: "default", label: "In Stock", row_ids: ["r2", "r4"] },
			{ group_id: "supply-on-order", label: "On Order", row_ids: ["r3"] },
			{ group_id: "supply-back-order", label: "Back Order", row_ids: ["r1"] },
		]);
	});

	it("puts every row in the default group when all share one supply", () => {
		const groups = buildSuggestedSplitGroups(
			cart(),
			{ r1: "On Order", r2: "On Order", r3: "On Order", r4: "On Order" },
			"default",
		);

		expect(groups).toEqual([
			{ group_id: "default", label: "On Order", row_ids: ["r1", "r2", "r3", "r4"] },
		]);
	});
});
