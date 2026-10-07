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
		applySupplyTypes(items, { r1: "Allocated" });
		(items[0] as any).rate = 99;

		expect(cartSupplySignature(items)).toBe(base);
	});

	it("takes the slowest supply when a cart row expands into several lines", () => {
		expect(
			supplyByRowId([
				{ posa_row_id: "r1", source: "Allocated" },
				{ posa_row_id: "r1", source: "Lead Time" },
				{ posa_row_id: "r1", source: "Pre Allocated" },
				{ posa_row_id: "r2", source: "Pre Allocated" },
				{ posa_row_id: "r2", source: "Allocated" },
				{ posa_row_id: "", source: "Allocated" },
			]),
		).toEqual({ r1: "Lead Time", r2: "Pre Allocated" });
	});

	it("stores, detects and clears supply types on cart rows", () => {
		const items = cart();
		const supplies = { r1: "Allocated", r2: "Pre Allocated", r3: "Lead Time" };
		applySupplyTypes(items, supplies);
		expect(hasCompleteSupplyTypes(items)).toBe(false);

		applySupplyTypes(items, { ...supplies, r4: "Allocated" });
		expect(hasCompleteSupplyTypes(items)).toBe(true);
		expect(storedSupplyByRowId(items)).toEqual({ ...supplies, r4: "Allocated" });

		clearSupplyTypes(items);
		expect(items.some((item) => "posa_supply_type" in item)).toBe(false);
		expect(hasCompleteSupplyTypes(items)).toBe(false);
	});

	it("builds one group per supply type, earliest supply first, keeping the default group", () => {
		const groups = buildSuggestedSplitGroups(
			cart(),
{ r1: "Lead Time", r2: "Allocated", r3: "Pre Allocated", r4: "Allocated" },
			"default",
		);

		expect(groups).toEqual([
			{ group_id: "default", label: "Allocated", row_ids: ["r2", "r4"] },
			{ group_id: "supply-pre-allocated", label: "Pre Allocated", row_ids: ["r3"] },
			{ group_id: "supply-lead-time", label: "Lead Time", row_ids: ["r1"] },
		]);
	});

	it("puts every row in the default group when all share one supply", () => {
		const groups = buildSuggestedSplitGroups(
			cart(),
			{ r1: "Pre Allocated", r2: "Pre Allocated", r3: "Pre Allocated", r4: "Pre Allocated" },
			"default",
		);

		expect(groups).toEqual([
			{ group_id: "default", label: "Pre Allocated", row_ids: ["r1", "r2", "r3", "r4"] },
		]);
	});
});
