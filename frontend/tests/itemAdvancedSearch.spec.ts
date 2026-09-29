import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	ITEM_ADVANCED_SEARCH_QUERY,
	openItemAdvancedSearch,
} from "../src/posapp/utils/itemAdvancedSearch";

describe("openItemAdvancedSearch", () => {
	let LinkSelector: ReturnType<typeof vi.fn>;

	beforeEach(() => {
		LinkSelector = vi.fn();
		(globalThis as any).frappe = { ui: { form: { LinkSelector } } };
	});

	afterEach(() => {
		delete (globalThis as any).frappe;
	});

	const openAndGetOpts = (params: Record<string, any> = {}) => {
		const onSelect = vi.fn();
		openItemAdvancedSearch({ onSelect, ...params });
		expect(LinkSelector).toHaveBeenCalledTimes(1);
		return { opts: LinkSelector.mock.calls[0][0], onSelect };
	};

	it("opens the Item LinkSelector pre-filled with the search text", () => {
		const { opts } = openAndGetOpts({ txt: "butterfly" });
		expect(opts.doctype).toBe("Item");
		expect(opts.txt).toBe("butterfly");
	});

	it("uses ERPNext's item_query with sales filters in the POS", () => {
		const { opts } = openAndGetOpts({ context: "pos", customer: "CUST-1" });
		const args: Record<string, any> = { txt: "x" };
		opts.target.set_custom_query(args);
		expect(args.query).toBe(ITEM_ADVANCED_SEARCH_QUERY);
		expect(args.filters).toEqual({ is_sales_item: 1, has_variants: 0, customer: "CUST-1" });
	});

	it("omits the customer filter when none is selected", () => {
		const { opts } = openAndGetOpts({ context: "sales-order", customer: null });
		const args: Record<string, any> = {};
		opts.target.set_custom_query(args);
		expect(args.filters).toEqual({ is_sales_item: 1, has_variants: 0 });
	});

	it("uses purchase filters in the purchase context", () => {
		const { opts } = openAndGetOpts({ context: "purchase", customer: "CUST-1" });
		const args: Record<string, any> = {};
		opts.target.set_custom_query(args);
		expect(args.filters).toEqual({ is_purchase_item: 1, has_variants: 0 });
	});

	it("passes the picked item code to onSelect", () => {
		const { opts, onSelect } = openAndGetOpts();
		// LinkSelector calls set_input then triggers change on a plain target.
		opts.target.set_input("CO-10BET");
		opts.target.$input.trigger("change");
		expect(onSelect).toHaveBeenCalledWith("CO-10BET");
	});
});
