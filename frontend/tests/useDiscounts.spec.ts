import { beforeEach, describe, expect, it, vi } from "vitest";

const toastShow = vi.fn();

vi.mock("../src/posapp/stores/toastStore", () => ({
	useToastStore: () => ({
		show: toastShow,
	}),
}));

import { useDiscounts } from "../src/posapp/composables/pos/shared/useDiscounts";

const makeContext = () => ({
	pos_profile: { currency: "USD" },
	price_list_currency: "USD",
	selected_currency: "USD",
	conversion_rate: 1,
	currency_precision: 2,
	float_precision: 4,
	forceUpdate: vi.fn(),
	calc_stock_qty: vi.fn(),
	flt(value: unknown, precision = 2) {
		const numeric = Number(value);
		if (!Number.isFinite(numeric)) {
			return 0;
		}
		return Number(numeric.toFixed(precision));
	},
});

const makeOfferItem = (overrides: Record<string, unknown> = {}) => ({
	rate: 100,
	base_rate: 100,
	price_list_rate: 100,
	base_price_list_rate: 100,
	discount_amount: 0,
	base_discount_amount: 0,
	discount_percentage: 0,
	qty: 1,
	_manual_rate_set: false,
	_manual_rate_set_from_uom: false,
	_offer_constraints: {},
	...overrides,
});

describe("useDiscounts offer price enforcement", () => {
	beforeEach(() => {
		toastShow.mockReset();
		(globalThis as any).__ = (text: string) => text;
		(globalThis as any).flt = (value: unknown, precision = 2) => {
			const numeric = Number(value);
			if (!Number.isFinite(numeric)) {
				return 0;
			}
			return Number(numeric.toFixed(precision));
		};
	});

	it("clamps rate edits to the floor derived from max discount amount", () => {
		const context = makeContext();
		const item = makeOfferItem({
			_offer_constraints: {
				max_base_discount_amount: 20,
			},
		});

		const { calcPrices } = useDiscounts();
		calcPrices(item, 60, { target: { id: "rate" } }, context);

		expect(item.base_rate).toBeCloseTo(80);
		expect(item.rate).toBeCloseTo(80);
		expect(item.base_discount_amount).toBeCloseTo(20);
		expect(item.discount_amount).toBeCloseTo(20);
		expect(item.discount_percentage).toBeCloseTo(20);
		expect(toastShow).toHaveBeenCalledWith(
			expect.objectContaining({
				title: "Rate adjusted to maximum allowed discount",
			}),
		);
	});

	it("restores previous values when discount amount exceeds offer criteria", () => {
		const context = makeContext();
		const item = makeOfferItem({
			_offer_constraints: {
				max_base_discount_amount: 20,
			},
		});

		const { calcPrices } = useDiscounts();
		calcPrices(item, 35, { target: { id: "discount_amount" } }, context);

		expect(item.base_rate).toBeCloseTo(100);
		expect(item.rate).toBeCloseTo(100);
		expect(item.base_discount_amount).toBeCloseTo(0);
		expect(item.discount_amount).toBeCloseTo(0);
		expect(toastShow).toHaveBeenCalledWith(
			expect.objectContaining({
				title: "Offer criteria exceeded",
			}),
		);
	});
});

describe("useDiscounts additional discount two-way sync", () => {
	beforeEach(() => {
		toastShow.mockReset();
		(globalThis as any).__ = (text: string) => text;
		(globalThis as any).flt = (value: unknown, precision = 2) => {
			const numeric = Number(value);
			if (!Number.isFinite(numeric)) {
				return 0;
			}
			return Number(numeric.toFixed(precision));
		};
	});

	const makeInvoiceContext = (overrides: Record<string, unknown> = {}) => ({
		pos_profile: {},
		Total: 200,
		isReturnInvoice: false,
		additional_discount: 0,
		additional_discount_percentage: 0,
		float_precision: 2,
		...overrides,
	});

	it("derives the amount from a percentage entry", () => {
		const context = makeInvoiceContext({ additional_discount_percentage: 10 });
		const { syncDiscountAmountFromPercentage } = useDiscounts();

		syncDiscountAmountFromPercentage(context);

		expect(context.additional_discount).toBeCloseTo(20);
	});

	it("derives the percentage from an amount entry", () => {
		const context = makeInvoiceContext({ additional_discount: 50 });
		const { syncDiscountPercentageFromAmount } = useDiscounts();

		syncDiscountPercentageFromAmount(context);

		expect(context.additional_discount_percentage).toBeCloseTo(25);
	});

	it("leaves a percentage entry alone when it already explains the amount", () => {
		const context = makeInvoiceContext({
			additional_discount: 66.6667,
			additional_discount_percentage: 33.3333,
		});
		const { syncDiscountPercentageFromAmount } = useDiscounts();

		syncDiscountPercentageFromAmount(context);

		expect(context.additional_discount_percentage).toBeCloseTo(33.3333);
	});

	it("zeroes the percentage when the amount is cleared", () => {
		const context = makeInvoiceContext({
			additional_discount: 0,
			additional_discount_percentage: 25,
		});
		const { syncDiscountPercentageFromAmount } = useDiscounts();

		syncDiscountPercentageFromAmount(context);

		expect(context.additional_discount_percentage).toBe(0);
	});

	it("negates the derived percentage on return invoices", () => {
		const context = makeInvoiceContext({
			isReturnInvoice: true,
			Total: -200,
			additional_discount: -20,
		});
		const { syncDiscountPercentageFromAmount } = useDiscounts();

		syncDiscountPercentageFromAmount(context);

		expect(context.additional_discount_percentage).toBeCloseTo(-10);
	});

	it("does not clamp while the percentage is still being typed", () => {
		const context = makeInvoiceContext({
			pos_profile: { posa_max_discount_allowed: 10 },
			additional_discount_percentage: 25,
		});
		const { syncDiscountAmountFromPercentage } = useDiscounts();

		syncDiscountAmountFromPercentage(context);

		expect(context.additional_discount).toBeCloseTo(50);
		expect(toastShow).not.toHaveBeenCalled();
	});

	it("applies the POS Profile ceiling when an amount entry is committed", () => {
		const context = makeInvoiceContext({
			pos_profile: { posa_max_discount_allowed: 10 },
			additional_discount: 50,
		});
		const { commitDiscountAmount } = useDiscounts();

		commitDiscountAmount(context);

		expect(context.additional_discount_percentage).toBeCloseTo(10);
		expect(context.additional_discount).toBeCloseTo(20);
		expect(toastShow).toHaveBeenCalledWith(
			expect.objectContaining({
				title: "Discount limited by POS Profile",
			}),
		);
	});

	it("leaves an amount entry inside the ceiling untouched", () => {
		const context = makeInvoiceContext({
			pos_profile: { posa_max_discount_allowed: 30 },
			additional_discount: 50,
		});
		const { commitDiscountAmount } = useDiscounts();

		commitDiscountAmount(context);

		expect(context.additional_discount).toBeCloseTo(50);
		expect(context.additional_discount_percentage).toBeCloseTo(25);
		expect(toastShow).not.toHaveBeenCalled();
	});
});
