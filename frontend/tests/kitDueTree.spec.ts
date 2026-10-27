import { describe, expect, it } from "vitest";
import { flattenKitDueTree, type KitDueTreeNode } from "../src/posapp/utils/kitDueTree";

const node = (item_code: string, children: KitDueTreeNode[] = []): KitDueTreeNode => ({
	item_code,
	item_name: item_code,
	qty_per: 1,
	total_qty: 1,
	is_kit_item: children.length ? 1 : 0,
	is_kit_set: 0,
	next_due_date: null,
	quantity_due_in: 0,
	cycle: 0,
	children,
});

const tree = node("SET", [node("KIT", [node("LEAF-A"), node("LEAF-B")]), node("LEAF-C")]);

describe("flattenKitDueTree", () => {
	it("returns nothing for an empty tree", () => {
		expect(flattenKitDueTree(null, new Set())).toEqual([]);
	});

	it("flattens depth-first with depths and child flags", () => {
		const rows = flattenKitDueTree(tree, new Set());
		expect(rows.map((r) => [r.node.item_code, r.depth, r.hasChildren])).toEqual([
			["SET", 0, true],
			["KIT", 1, true],
			["LEAF-A", 2, false],
			["LEAF-B", 2, false],
			["LEAF-C", 1, false],
		]);
	});

	it("hides descendants of collapsed rows only", () => {
		const kitKey = flattenKitDueTree(tree, new Set())[1].key;
		const rows = flattenKitDueTree(tree, new Set([kitKey]));
		expect(rows.map((r) => r.node.item_code)).toEqual(["SET", "KIT", "LEAF-C"]);
	});

	it("gives the same component under different parents distinct keys", () => {
		const shared = node("ROOT", [node("K1", [node("X")]), node("K2", [node("X")])]);
		const keys = flattenKitDueTree(shared, new Set())
			.filter((r) => r.node.item_code === "X")
			.map((r) => r.key);
		expect(new Set(keys).size).toBe(2);
	});
});
