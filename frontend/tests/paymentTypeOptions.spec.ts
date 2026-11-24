import { describe, expect, it } from "vitest";

import {
	partnerPaymentNote,
	resolvePaymentTypeOptions,
	type PaymentTypeOptions,
} from "../src/posapp/utils/paymentTypeOptions";

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

describe("partnerPaymentNote", () => {
	const t = (text: string) => text;
	const opts = (o: Partial<PaymentTypeOptions>): PaymentTypeOptions => ({
		showSubmitWithoutPayment: false,
		showOnAccount: false,
		showProforma: false,
		...o,
	});

	it("keeps the Place Order text when only Place Order is available", () => {
		expect(partnerPaymentNote(opts({ showSubmitWithoutPayment: true }), t)).toEqual({
			title: "Place Order",
			lines: ["No payment is taken here. Agile will invoice this order."],
		});
	});

	it("explains Pro Forma and On Account separately", () => {
		const note = partnerPaymentNote(opts({ showProforma: true, showOnAccount: true }), t);
		expect(note.title).toBe("How would you like to place this order?");
		expect(note.lines).toHaveLength(2);
		expect(note.lines[0]).toMatch(/^Pro Forma: .*payment link.*held until it is paid/);
		expect(note.lines[1]).toMatch(/^On Account: no payment is taken now/);
	});

	it("explains Pro Forma alone without claiming no payment is taken", () => {
		const note = partnerPaymentNote(opts({ showProforma: true }), t);
		expect(note.lines).toHaveLength(1);
		expect(note.lines[0]).toMatch(/^Pro Forma:/);
	});

	it("adds the Place Order line when it is still shown alongside", () => {
		const note = partnerPaymentNote(opts({ showOnAccount: true, showSubmitWithoutPayment: true }), t);
		expect(note.lines).toHaveLength(2);
		expect(note.lines[1]).toBe("No payment is taken here. Agile will invoice this order.");
	});
});
