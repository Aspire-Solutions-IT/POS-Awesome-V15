// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

import PaymentActionButtons from "../src/posapp/components/pos/payments/PaymentActionButtons.vue";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});

const ButtonStub = defineComponent({
	emits: ["click"],
	setup(_, { slots, emit }) {
		return () => h("button", { onClick: () => emit("click") }, slots.default?.());
	},
});

const mountButtons = (props: Record<string, any> = {}) =>
	mount(PaymentActionButtons, {
		props,
		global: { components: { VCard: BoxStub, VRow: BoxStub, VCol: BoxStub, VBtn: ButtonStub } },
	});

const labels = (wrapper: any) => wrapper.findAll("button").map((b: any) => b.text());

describe("PaymentActionButtons payment types", () => {
	beforeEach(() => {
		vi.stubGlobal("__", (value: string) => value);
		(globalThis as any).window.__ = (value: string) => value;
		(globalThis as any).frappe = { boot: {} };
	});

	it("shows neither button by default (staff behaviour unchanged)", () => {
		const wrapper = mountButtons({ showSubmitWithoutPayment: true });
		expect(labels(wrapper)).toEqual(["Submit", "Submit Without Payment", "Cancel Payment"]);
	});

	it("emits submit-on-account and submit-proforma through listener props", async () => {
		const onAccount = vi.fn();
		const onProforma = vi.fn();
		const wrapper = mountButtons({
			showOnAccount: true,
			showProforma: true,
			"onSubmit-on-account": onAccount,
			"onSubmit-proforma": onProforma,
		});
		const buttons = wrapper.findAll("button");
		await buttons.find((b: any) => b.text() === "On Account")!.trigger("click");
		await buttons.find((b: any) => b.text() === "Pro Forma")!.trigger("click");
		expect(onAccount).toHaveBeenCalledTimes(1);
		expect(onProforma).toHaveBeenCalledTimes(1);
	});

	it("shows only the enabled type", () => {
		expect(labels(mountButtons({ showOnAccount: true }))).toContain("On Account");
		expect(labels(mountButtons({ showOnAccount: true }))).not.toContain("Pro Forma");
		expect(labels(mountButtons({ showProforma: true }))).not.toContain("On Account");
	});
});
