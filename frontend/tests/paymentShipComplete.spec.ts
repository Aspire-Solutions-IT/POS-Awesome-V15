// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PaymentAdditionalInfo from "../src/posapp/components/pos/payments/PaymentAdditionalInfo.vue";

const passthrough = defineComponent({
	render() {
		return h("div", this.$slots.default?.());
	},
});

const mountInfo = (props: Record<string, unknown>) => {
	const onSplit = vi.fn();
	const wrapper = mount(PaymentAdditionalInfo, {
		props: {
			invoiceDoc: {},
			posProfile: { posa_allow_sales_order: 1 },
			invoiceType: "Order",
			"onUpdate:splitDelivery": onSplit,
			...props,
		},
		global: {
			mocks: { $frappe: { _: (text: string) => text } },
			components: {
				VRow: passthrough,
				VCol: passthrough,
				VCheckbox: {
					props: ["label"],
					render() {
						return h("label", { "data-test": "split-toggle" }, (this as any).label);
					},
				},
				VTextField: true,
				VTextarea: true,
				VAutocomplete: true,
				VSelect: true,
				VChip: true,
				VIcon: true,
				VBtn: true,
				VSwitch: true,
				VMenu: true,
				VDateInput: true,
			},
		},
	});
	return { wrapper, onSplit };
};

describe("PaymentAdditionalInfo ship complete", () => {
	beforeEach(() => {
		(globalThis as any).window.__ = (text: string) => text;
		(globalThis as any).window.frappe = { _: (text: string) => text };
		(globalThis as any).$frappe = (globalThis as any).window.frappe;
	});

	it("shows the no-partial-delivery note and no split toggle for a ship-complete charge", () => {
		const { wrapper } = mountInfo({ shipComplete: true, showSplitDelivery: false });
		expect(wrapper.find("[data-test='ship-complete-note']").text()).toBe(
			"This order ships complete: no partial deliveries",
		);
		expect(wrapper.find("[data-test='split-toggle']").exists()).toBe(false);
	});

	it("keeps the split toggle and shows no note on a normal charge", () => {
		const { wrapper } = mountInfo({ shipComplete: false, showSplitDelivery: true });
		expect(wrapper.find("[data-test='ship-complete-note']").exists()).toBe(false);
		expect(wrapper.find("[data-test='split-toggle']").exists()).toBe(true);
	});
});
