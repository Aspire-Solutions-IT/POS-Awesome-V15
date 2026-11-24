import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/offline/index", () => ({
	isOffline: () => false,
}));

vi.mock("../src/posapp/stores/toastStore", () => ({
	useToastStore: () => ({ show: vi.fn() }),
}));

import { useStockUtils } from "../src/posapp/composables/pos/shared/useStockUtils";
import { setChargePricing } from "../src/posapp/utils/chargePricingContext";

const makeItem = () => ({
	item_code: "ITEM-1",
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
	rate: 10,
	base_rate: 10,
	price_list_rate: 10,
	base_price_list_rate: 10,
	qty: 1,
	item_uoms: [
		{ uom: "Nos", conversion_factor: 1 },
		{ uom: "Box", conversion_factor: 6 },
	],
});

const makeContext = (customer: string) => ({
	customer,
	get_price_list: () => "Profile List",
	pos_profile: { currency: "GBP" },
	selected_currency: "GBP",
	forceUpdate: vi.fn(),
});

describe("calcUom price lookup", () => {
	let calls: any[];

	beforeEach(() => {
		calls = [];
		setChargePricing(null);
		(globalThis as any).__ = (text: string) => text;
		(globalThis as any).frappe = {
			call: vi.fn(async (opts: any) => {
				calls.push(opts);
				return { message: 60 };
			}),
		};
	});

	it("sends the selected customer and the order's delivery charge with the UOM", async () => {
		setChargePricing({ name: "FOB", price_list: "FOB List", price_list_overrides_customer: 1 });
		const { calcUom } = useStockUtils();
		await calcUom(makeItem(), "Box", makeContext("CUST-A"));

		expect(calls).toHaveLength(1);
		expect(calls[0].method).toBe("posawesome.posawesome.api.items.get_price_for_uom");
		expect(calls[0].args).toMatchObject({
			item_code: "ITEM-1",
			uom: "Box",
			customer: "CUST-A",
			delivery_charge: "FOB",
		});
	});

	it("does not reuse a quote across customers or charges on the same list", async () => {
		const context: any = makeContext("CUST-A");
		const { calcUom } = useStockUtils();

		await calcUom(makeItem(), "Box", context);
		await calcUom(makeItem(), "Box", context);
		expect(calls).toHaveLength(1); // same customer and charge: cached

		context.customer = "CUST-B";
		await calcUom(makeItem(), "Box", context);
		expect(calls).toHaveLength(2); // another customer asks again
		expect(calls[1].args.customer).toBe("CUST-B");

		setChargePricing({ name: "DDP", price_list: "DDP List", price_list_overrides_customer: 1 });
		await calcUom(makeItem(), "Box", context);
		expect(calls).toHaveLength(3); // another charge asks again
		expect(calls[2].args.delivery_charge).toBe("DDP");
	});

	it("sends no delivery charge when the order has none", async () => {
		const { calcUom } = useStockUtils();
		await calcUom(makeItem(), "Box", makeContext("CUST-A"));
		expect(calls[0].args).not.toHaveProperty("delivery_charge");
	});
});
