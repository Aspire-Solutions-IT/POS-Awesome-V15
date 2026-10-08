// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

import DeliveryEstimateDialog from "../src/posapp/components/pos/invoice/DeliveryEstimateDialog.vue";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});

const ButtonStub = defineComponent({
	emits: ["click"],
	setup(_, { attrs, slots, emit }) {
		return () => h("button", { "data-test": attrs["data-test"], onClick: () => emit("click") }, slots.default?.());
	},
});

const estimate = {
	window: "12-10-2026 - 16-10-2026",
	lines: [{ item_code: "TABLE", item_name: "Table", qty: 1, source: "In Stock" }],
};

function mountDialog(props: Record<string, any>) {
	return mount(DeliveryEstimateDialog, {
		props: { modelValue: true, estimate, ...props },
		global: {
			components: {
				VDialog: BoxStub, VCard: BoxStub, VCardText: BoxStub, VCardActions: BoxStub,
				VSpacer: BoxStub, VTable: BoxStub, VBtn: ButtonStub,
			},
		},
	});
}

describe("DeliveryEstimateDialog", () => {
	beforeEach(() => {
		vi.stubGlobal("__", (value: string) => value);
	});

	it("only offers Close when opened from the Estimate Delivery button", () => {
		const wrapper = mountDialog({});

		expect(wrapper.find('[data-test="estimate-window"]').text()).toBe("12-10-2026 - 16-10-2026");
		expect(wrapper.find('[data-test="estimate-continue-to-payment"]').exists()).toBe(false);
		expect(wrapper.text()).toContain("Close");
	});

	it("offers Continue to Payment and Back to Cart when opened from PAY", async () => {
		const onContinue = vi.fn();
		const onUpdate = vi.fn();
		const wrapper = mountDialog({ continueToPayment: true, onContinue, "onUpdate:modelValue": onUpdate });

		await wrapper.find('[data-test="estimate-continue-to-payment"]').trigger("click");
		expect(onContinue).toHaveBeenCalledTimes(1);

		await wrapper.find('[data-test="estimate-back-to-cart"]').trigger("click");
		expect(onUpdate).toHaveBeenCalledWith(false);
	});
});
