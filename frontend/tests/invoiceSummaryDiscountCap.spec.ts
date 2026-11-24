// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import InvoiceSummary from "../src/posapp/components/pos/invoice/InvoiceSummary.vue";

const TextFieldStub = defineComponent({
	props: { modelValue: [String, Number], name: String },
	emits: ["update:modelValue", "focus", "blur", "change"],
	setup(props, { emit }) {
		return () =>
			h("input", {
			name: props.name,
			value: props.modelValue,
			onInput: (event: Event) => emit("update:modelValue", (event.target as HTMLInputElement).value),
			onFocus: () => emit("focus"),
			onBlur: () => emit("blur"),
			onChange: () => emit("change"),
		});
	},
});
const BoxStub = defineComponent({ setup(_, { slots }) { return () => h("div", {}, slots.default?.()); } });

describe("Active Sale discount cap display", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.stubGlobal("__", (value: string) => value);
		vi.stubGlobal("frappe", { _: (value: string) => value });
		window.innerWidth = 1100;
	});

	it("shows the capped percentage after a focused 70% entry is committed", async () => {
		let wrapper: ReturnType<typeof mount>;
		wrapper = mount(InvoiceSummary, {
			props: {
				pos_profile: { currency: "GBP", posa_allow_user_to_edit_additional_discount: true },
				additional_discount: 0,
				additional_discount_percentage: 0,
				formatCurrency: (value: number) => String(value),
				formatFloat: (value: number) => String(value),
				currencySymbol: () => "£",
				isNumber: () => true,
				onUpdate_discount_umount: () => wrapper.setProps({ additional_discount: 157.5, additional_discount_percentage: 50 }),
			},
			global: {
				mocks: { __: (value: string) => value, frappe: { _: (value: string) => value } },
				components: { VTextField: TextFieldStub, VCard: BoxStub, VRow: BoxStub, VCol: BoxStub },
				stubs: { InvoiceActionButtons: true, StainguardToggle: true },
			},
		});

		const percentage = wrapper.find('input[name="posa-additional-discount-percentage"]');
		await percentage.trigger("focus");
		await percentage.setValue("70");
		await nextTick();

		expect((percentage.element as HTMLInputElement).value).toBe("50");
		expect((wrapper.find('input[name="posa-additional-discount"]').element as HTMLInputElement).value).toBe("157.5");
	});
});
