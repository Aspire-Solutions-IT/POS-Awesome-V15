// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

import InvoiceActionButtons from "../src/posapp/components/pos/invoice/InvoiceActionButtons.vue";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});

const ButtonStub = defineComponent({
	props: { prependIcon: String, loading: Boolean },
	emits: ["click"],
	setup(props, { slots, emit }) {
		return () =>
			h(
				"button",
				{ "data-icon": props.prependIcon, "data-loading": String(props.loading), onClick: () => emit("click") },
				slots.default?.(),
			);
	},
});

function mountButtons(props: Record<string, any>) {
	return mount(InvoiceActionButtons, {
		props,
		global: { components: { VRow: BoxStub, VCol: BoxStub, VBtn: ButtonStub } },
	});
}

const estimateButton = (wrapper: ReturnType<typeof mountButtons>) =>
	wrapper.find('button[data-icon="mdi-truck-fast-outline"]');

describe("InvoiceActionButtons estimate delivery", () => {
	beforeEach(() => {
		vi.stubGlobal("__", (value: string) => value);
	});

	it("is hidden when the cart does not submit as a Sales Order", () => {
		const wrapper = mountButtons({ pos_profile: { posa_create_only_sales_order: 0 } });

		expect(estimateButton(wrapper).exists()).toBe(false);
	});

	it("emits estimate-delivery when clicked in Sales Order mode", async () => {
		const onEstimateDelivery = vi.fn();
		const wrapper = mountButtons({
			pos_profile: { posa_create_only_sales_order: 1 },
			estimateLoading: true,
			onEstimateDelivery,
		});

		const button = estimateButton(wrapper);
		expect(button.exists()).toBe(true);
		expect(button.text()).toBe("Estimate Delivery");
		expect(button.attributes("data-loading")).toBe("true");

		await button.trigger("click");
		expect(onEstimateDelivery).toHaveBeenCalledTimes(1);
	});
});
