// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

import StainguardToggle from "../src/posapp/components/pos/invoice/StainguardToggle.vue";

const CheckboxStub = defineComponent({
	props: { modelValue: Boolean },
	emits: ["update:modelValue"],
	setup(props, { attrs, emit }) {
		return () =>
			h("input", {
				type: "checkbox",
				"data-test": attrs["data-test"],
				checked: props.modelValue,
				onChange: (event: Event) => emit("update:modelValue", (event.target as HTMLInputElement).checked),
			});
	},
});

const SpinnerStub = defineComponent({ setup: () => () => h("i", { "data-test": "spinner" }) });

function mountToggle(props: Record<string, any> = {}) {
	return mount(StainguardToggle, {
		props: { available: true, modelValue: false, ...props },
		global: { components: { VCheckbox: CheckboxStub, VProgressCircular: SpinnerStub } },
	});
}

describe("StainguardToggle", () => {
	beforeEach(() => {
		(window as any).__ = (value: string) => value;
	});

	it("renders nothing when cover is not available for the cart", () => {
		const wrapper = mountToggle({ available: false });

		expect(wrapper.find('[data-test="stainguard-toggle-root"]').exists()).toBe(false);
	});

	it("shows the Stainguard logo from the app's own assets", () => {
		const logo = mountToggle().find('[data-test="stainguard-logo"]');

		expect(logo.attributes("src")).toBe("/assets/posawesome/images/stainguard-logo.jpg");
		expect(logo.attributes("alt")).toBe("Stainguard");
	});

	it("emits the ticked state", async () => {
		const onUpdate = vi.fn();
		const wrapper = mountToggle({ "onUpdate:modelValue": onUpdate });

		await wrapper.find('[data-test="stainguard-toggle"]').setValue(true);

		expect(onUpdate).toHaveBeenCalledWith(true);
	});

	it("shows nothing under the tick box while it is unticked", () => {
		const wrapper = mountToggle({ status: { item_name: "Stainguard 1", rate: 50 } });

		expect(wrapper.find('[data-test="stainguard-detail"]').exists()).toBe(false);
	});

	it("shows the cover and its price once ticked", () => {
		const formatCurrency = (value: number) => `£${value.toFixed(2)}`;
		const wrapper = mountToggle({
			modelValue: true,
			formatCurrency,
			status: { loading: false, item_name: "Stainguard Protect 6", rate: 50, message: "" },
		});

		expect(wrapper.find('[data-test="stainguard-detail"]').text()).toContain("Stainguard Protect 6");
		expect(wrapper.find('[data-test="stainguard-price"]').text()).toBe("£50.00");
	});

	it("shows a spinner while the cover is being worked out", () => {
		const wrapper = mountToggle({ modelValue: true, status: { loading: true, item_name: "", rate: 0, message: "" } });

		expect(wrapper.find('[data-test="spinner"]').exists()).toBe(true);
	});

	it("explains when no cover fits the order value", () => {
		const wrapper = mountToggle({
			modelValue: true,
			status: { loading: false, item_name: "", rate: 0, message: "No Stainguard cover for this order value" },
		});

		expect(wrapper.find('[data-test="stainguard-detail"]').text()).toBe("No Stainguard cover for this order value");
	});
});
