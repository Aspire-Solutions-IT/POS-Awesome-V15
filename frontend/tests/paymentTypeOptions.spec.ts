import { describe, expect, it } from "vitest";

import { resolvePaymentTypeOptions } from "../src/posapp/utils/paymentTypeOptions";

const base = {
	isPartner: false,
	isOrder: true,
	createOnlySalesOrder: true,
	allowOnAccount: false,
	allowProforma: false,
};

describe("resolvePaymentTypeOptions", () => {
	it("keeps Place Order for a partner whose profile offers neither On Account nor Pro Forma", () => {
		expect(resolvePaymentTypeOptions({ ...base, isPartner: true })).toEqual({
			showSubmitWithoutPayment: true,
			showOnAccount: false,
			showProforma: false,
		});
	});

	it("replaces Place Order with whichever of On Account / Pro Forma a partner has", () => {
		expect(resolvePaymentTypeOptions({ ...base, isPartner: true, allowOnAccount: true })).toEqual({
			showSubmitWithoutPayment: false,
			showOnAccount: true,
			showProforma: false,
		});
		expect(resolvePaymentTypeOptions({ ...base, isPartner: true, allowProforma: true })).toEqual({
			showSubmitWithoutPayment: false,
			showOnAccount: false,
			showProforma: true,
		});
		expect(
			resolvePaymentTypeOptions({ ...base, isPartner: true, allowOnAccount: true, allowProforma: true }),
		).toEqual({ showSubmitWithoutPayment: false, showOnAccount: true, showProforma: true });
	});

	it("keeps Place Order for a partner when the types are switched on but this is not an order-only profile", () => {
		const result = resolvePaymentTypeOptions({
			...base,
			isPartner: true,
			createOnlySalesOrder: false,
			allowOnAccount: true,
			allowProforma: true,
		});
		expect(result).toEqual({ showSubmitWithoutPayment: true, showOnAccount: false, showProforma: false });
	});

	it("leaves staff unchanged: Submit Without Payment on order-only profiles, On Account when allowed, never Pro Forma", () => {
		expect(resolvePaymentTypeOptions(base)).toEqual({
			showSubmitWithoutPayment: true,
			showOnAccount: false,
			showProforma: false,
		});
		expect(resolvePaymentTypeOptions({ ...base, allowOnAccount: true, allowProforma: true })).toEqual({
			showSubmitWithoutPayment: true,
			showOnAccount: true,
			showProforma: false,
		});
		expect(resolvePaymentTypeOptions({ ...base, createOnlySalesOrder: false })).toEqual({
			showSubmitWithoutPayment: false,
			showOnAccount: false,
			showProforma: false,
		});
		expect(resolvePaymentTypeOptions({ ...base, isOrder: false })).toEqual({
			showSubmitWithoutPayment: false,
			showOnAccount: false,
			showProforma: false,
		});
	});
});
