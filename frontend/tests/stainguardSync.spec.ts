// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

const apiCall = vi.fn();
vi.mock("../src/posapp/services/api", () => ({ default: { call: (...args: any[]) => apiCall(...args) } }));

import {
	emptyStainguardStatus,
	flushStainguardSync,
	scheduleStainguardSync,
	stainguardAvailable,
	syncStainguard,
} from "../src/posapp/components/pos/invoice_utils/stainguard";

const OFFER = "customer_due_dates.staingard.pos.get_stainguard_offer";
const SEARCH = "posawesome.posawesome.api.items.search_items_by_code";

function context(overrides: Record<string, any> = {}) {
	const ctx: Record<string, any> = {
		invoiceType: "Order",
		isReturnInvoice: false,
		pos_profile: { name: "Main", posa_enable_stainguard: 1 },
		customer: "CUST-1",
		items: [
			{ item_code: "SOFA", qty: 1, rate: 1000 },
			{ item_code: "TABLE", qty: 2, rate: 100 },
		],
		subtotal: 1250,
		delivery_charges_rate: 50,
		stainguard_enabled: true,
		stainguard_item_code: null,
		stainguard_status: emptyStainguardStatus(),
		stainguard_signature: "cart-1",
		flt: (value: any) => Number(value || 0),
		get_price_list: () => "Standard Selling",
		add_item: vi.fn(async (item: any) => {
			ctx.items.push(item);
		}),
		remove_item: vi.fn((line: any) => {
			ctx.items = ctx.items.filter((item: any) => item !== line);
		}),
		...overrides,
	};
	return ctx;
}

const coverRow = (rate = 40) => ({ item_code: "SG-1", item_name: "Stainguard 1", qty: 1, rate });

describe("Stainguard cover sync", () => {
	beforeEach(() => {
		apiCall.mockReset();
		vi.useRealTimers();
		vi.stubGlobal("__", (value: string, args: any[] = []) =>
			args.reduce((text, arg, index) => text.replace(`{${index}}`, arg), value),
		);
		vi.spyOn(console, "error").mockImplementation(() => {});
	});

	describe("availability", () => {
		it.each([
			["the profile has not enabled it", { pos_profile: { posa_enable_stainguard: 0 } }, false],
			["the cart is not an order", { invoiceType: "Invoice" }, false],
			["it is a return", { isReturnInvoice: true }, false],
			["an order on an enabled profile", {}, true],
		])("%s", (_label, overrides, expected) => {
			expect(stainguardAvailable(context(overrides))).toBe(expected);
		});
	});

	it("adds the cover for the total without the delivery charge", async () => {
		apiCall.mockResolvedValueOnce({ offer: { item_code: "SG-1", item_name: "Stainguard 1" }, cart_item_codes: [] });
		apiCall.mockResolvedValueOnce([{ item_code: "SG-1", item_name: "Stainguard 1", rate: 40 }]);
		const ctx = context();

		await syncStainguard(ctx);

		const [method, args] = apiCall.mock.calls[0];
		expect(method).toBe(OFFER);
		expect(args.total).toBe(1200);
		expect(JSON.parse(args.lines)).toEqual([
			{ item_code: "SOFA", amount: 1000 },
			{ item_code: "TABLE", amount: 200 },
		]);
		expect(apiCall.mock.calls[1][0]).toBe(SEARCH);
		expect(apiCall.mock.calls[1][1]).toMatchObject({
			pos_profile: "Main",
			price_list: "Standard Selling",
			customer: "CUST-1",
			search_value: "SG-1",
			exact: 1,
		});
		expect(ctx.add_item).toHaveBeenCalledWith(
			expect.objectContaining({ item_code: "SG-1", qty: 1, _skip_row_expansion: true }),
		);
		expect(ctx.stainguard_item_code).toBe("SG-1");
		expect(ctx.stainguard_status).toMatchObject({ loading: false, item_name: "Stainguard 1", rate: 40 });
	});

	it("leaves a cover that is already on the right band alone", async () => {
		const cover = coverRow();
		apiCall.mockResolvedValueOnce({ offer: { item_code: "SG-1" }, cart_item_codes: ["SG-1"] });
		const ctx = context({ items: [{ item_code: "SOFA", qty: 1, rate: 1000 }, cover] });

		await syncStainguard(ctx);

		expect(ctx.add_item).not.toHaveBeenCalled();
		expect(ctx.remove_item).not.toHaveBeenCalled();
		expect(apiCall).toHaveBeenCalledTimes(1);
		expect(ctx.stainguard_item_code).toBe("SG-1");
	});

	it("swaps the cover when the cart moves to another band", async () => {
		const oldCover = { item_code: "SG-0", item_name: "Stainguard 0", qty: 1, rate: 20 };
		apiCall.mockResolvedValueOnce({ offer: { item_code: "SG-1" }, cart_item_codes: ["SG-0"] });
		apiCall.mockResolvedValueOnce([{ item_code: "SG-1", item_name: "Stainguard 1", rate: 40 }]);
		const ctx = context({
			items: [{ item_code: "SOFA", qty: 1, rate: 1000 }, oldCover],
			stainguard_item_code: "SG-0",
		});

		await syncStainguard(ctx);

		expect(ctx.remove_item).toHaveBeenCalledWith(oldCover);
		expect(ctx.items.map((item: any) => item.item_code)).toEqual(["SOFA", "SG-1"]);
		expect(ctx.stainguard_item_code).toBe("SG-1");
	});

	it("removes the cover and says so when no band covers the order", async () => {
		const cover = coverRow();
		apiCall.mockResolvedValueOnce({ offer: null, cart_item_codes: ["SG-1"] });
		const ctx = context({ items: [{ item_code: "SOFA", qty: 1, rate: 9000 }, cover], stainguard_item_code: "SG-1" });

		await syncStainguard(ctx);

		expect(ctx.remove_item).toHaveBeenCalledWith(cover);
		expect(ctx.stainguard_item_code).toBeNull();
		expect(ctx.stainguard_status.message).toBe("No Stainguard cover for this order value");
	});

	it("takes the cover out when unticked, without asking the server", async () => {
		const cover = coverRow();
		const ctx = context({
			items: [{ item_code: "SOFA", qty: 1, rate: 1000 }, cover],
			stainguard_item_code: "SG-1",
			stainguard_enabled: false,
		});

		await syncStainguard(ctx);

		expect(apiCall).not.toHaveBeenCalled();
		expect(ctx.items.map((item: any) => item.item_code)).toEqual(["SOFA"]);
		expect(ctx.stainguard_item_code).toBeNull();
		expect(ctx.stainguard_status).toEqual(emptyStainguardStatus());
	});

	it("does nothing while unticked with no cover of its own in the cart", async () => {
		const ctx = context({ stainguard_enabled: false });

		await syncStainguard(ctx);

		expect(apiCall).not.toHaveBeenCalled();
		expect(ctx.remove_item).not.toHaveBeenCalled();
	});

	it("takes the cover out when the cart stops being an order", async () => {
		const cover = coverRow();
		const ctx = context({
			invoiceType: "Invoice",
			items: [{ item_code: "SOFA", qty: 1, rate: 1000 }, cover],
			stainguard_item_code: "SG-1",
		});

		await syncStainguard(ctx);

		expect(apiCall).not.toHaveBeenCalled();
		expect(ctx.items.map((item: any) => item.item_code)).toEqual(["SOFA"]);
	});

	it("waits for a customer and items before looking anything up", async () => {
		await syncStainguard(context({ customer: "" }));
		await syncStainguard(context({ items: [] }));

		expect(apiCall).not.toHaveBeenCalled();
	});

	it("discards an answer for a cart that has since changed and asks again", async () => {
		const ctx = context();
		apiCall.mockImplementationOnce(async () => {
			ctx.stainguard_signature = "cart-2";
			return { offer: { item_code: "SG-OLD" }, cart_item_codes: [] };
		});
		apiCall.mockResolvedValueOnce({ offer: null, cart_item_codes: [] });

		await syncStainguard(ctx);

		expect(ctx.add_item).not.toHaveBeenCalled();
		expect(apiCall).toHaveBeenCalledTimes(2);
		expect(apiCall.mock.calls.every(([method]) => method === OFFER)).toBe(true);
	});

	it("never breaks the cart when the lookup fails", async () => {
		apiCall.mockRejectedValueOnce(new Error("offline"));
		const ctx = context();

		await expect(syncStainguard(ctx)).resolves.toBeUndefined();

		expect(ctx.add_item).not.toHaveBeenCalled();
		expect(ctx.stainguard_status.loading).toBe(false);
	});

	it("says so when the cover is not sellable in the POS", async () => {
		apiCall.mockResolvedValueOnce({ offer: { item_code: "SG-1" }, cart_item_codes: [] });
		apiCall.mockResolvedValueOnce([]);
		const ctx = context();

		await syncStainguard(ctx);

		expect(ctx.add_item).not.toHaveBeenCalled();
		expect(ctx.stainguard_status.message).toBe("Stainguard item SG-1 is not available in the POS");
	});

	it("batches a burst of cart edits into one lookup", async () => {
		vi.useFakeTimers();
		apiCall.mockResolvedValue({ offer: null, cart_item_codes: [] });
		const ctx = context();

		scheduleStainguardSync(ctx);
		scheduleStainguardSync(ctx);
		scheduleStainguardSync(ctx);
		await vi.advanceTimersByTimeAsync(500);

		expect(apiCall).toHaveBeenCalledTimes(1);
	});

	it("runs a pending sync straight away when PAY is pressed", async () => {
		vi.useFakeTimers();
		apiCall.mockResolvedValue({ offer: null, cart_item_codes: [] });
		const ctx = context();

		scheduleStainguardSync(ctx);
		await flushStainguardSync(ctx);

		expect(apiCall).toHaveBeenCalledTimes(1);

		await vi.advanceTimersByTimeAsync(500);
		expect(apiCall).toHaveBeenCalledTimes(1);
	});
});
