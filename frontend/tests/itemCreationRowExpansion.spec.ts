// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

import { useItemCreation } from "../src/posapp/composables/pos/items/addition/useItemCreation";

function newItem(item: Record<string, any>) {
	const context: Record<string, any> = {
		pos_profile: { currency: "GBP", warehouse: "Stores", default_ns_warehouse: "NS Store" },
		expanded: [],
		makeid: () => "row-1",
	};
	const { getNewItem } = useItemCreation() as any;
	const created = getNewItem({ item_name: "Item", rate: 10, ...item }, context);
	return { created, context };
}

describe("getNewItem row expansion", () => {
	beforeEach(() => {
		vi.stubGlobal("__", (value: string) => value);
	});

	it("expands NS item rows for editing", () => {
		const { context } = newItem({ item_code: "NS-SOFA" });

		expect(context.expanded).toEqual(["row-1"]);
	});

	it("leaves an NS row collapsed when the line opts out", () => {
		const { created, context } = newItem({ item_code: "NS-STP6B-999", _skip_row_expansion: true });

		expect(context.expanded).toEqual([]);
		expect(created.warehouse).toBe("NS Store");
	});

	it("still expands serial-tracked rows that are not opting out", () => {
		const { context } = newItem({ item_code: "SOFA", has_serial_no: 1 });

		expect(context.expanded).toEqual(["row-1"]);
	});
});
