// @vitest-environment jsdom

import { flushPromises, mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("../src/posapp/services/api", () => ({ default: { call: (...args: unknown[]) => call(...args) } }));

import DhdAddressForm from "../src/posapp/components/pos/payments/DhdAddressForm.vue";
import PaymentAdditionalInfo from "../src/posapp/components/pos/payments/PaymentAdditionalInfo.vue";
import {
	canShowAddAddressAction,
	isDhdCharge,
	orderAddressErrorMessage,
} from "../src/posapp/services/orderAddressService";

const passthrough = defineComponent({
	render() {
		return h("div", this.$slots.default?.());
	},
});

const TextField = defineComponent({
	props: ["modelValue", "label"],
	emits: ["update:modelValue"],
	render() {
		return h("input", {
			value: (this as any).modelValue,
			onInput: (e: Event) => (this as any).$emit("update:modelValue", (e.target as HTMLInputElement).value),
		});
	},
});

const Btn = defineComponent({
	props: ["disabled", "loading"],
	render() {
		return h("button", { disabled: (this as any).disabled, type: "button" }, this.$slots.default?.());
	},
});

const components = {
	VRow: passthrough,
	VCol: passthrough,
	VTextField: TextField,
	VBtn: Btn,
	VTextarea: true,
	VAutocomplete: true,
	VCheckbox: true,
	VChip: true,
};

const fill = async (wrapper: any, values: Record<string, string>) => {
	for (const [test, value] of Object.entries(values)) {
		await wrapper.find(`[data-test='${test}']`).setValue(value);
	}
};

const GOOD = {
	"dhd-line1": "1 High St",
	"dhd-city": "Leeds",
	"dhd-postcode": "LS1 1AA",
};

describe("DhdAddressForm", () => {
	beforeEach(() => {
		call.mockReset();
		(globalThis as any).window.__ = (text: string) => text;
	});

	const mountForm = () => {
		const onSaved = vi.fn();
		const wrapper = mount(DhdAddressForm, {
			props: { customer: "CUST-1", deliveryCharge: "Home Delivery", onSaved },
			global: { components },
		});
		return { wrapper, onSaved };
	};

	it("defaults the country and keeps Save disabled until the required fields are filled", async () => {
		const { wrapper } = mountForm();
		expect((wrapper.find("[data-test='dhd-country']").element as HTMLInputElement).value).toBe(
			"United Kingdom",
		);
		expect(wrapper.find("[data-test='dhd-save']").attributes("disabled")).toBeDefined();
		await fill(wrapper, GOOD);
		expect(wrapper.find("[data-test='dhd-save']").attributes("disabled")).toBeUndefined();
	});

	it("does not call the server while typing, only on Save, with a POST", async () => {
		call.mockResolvedValue({ name: "CUST-1-Shipping-ab12", created: true });
		const { wrapper, onSaved } = mountForm();
		await fill(wrapper, { ...GOOD, "dhd-county": " West Yorks ", "dhd-phone": "0113" });
		expect(call).not.toHaveBeenCalled();

		await wrapper.find("[data-test='dhd-save']").trigger("click");
		await flushPromises();

		expect(call).toHaveBeenCalledTimes(1);
		expect(call).toHaveBeenCalledWith(
			"posawesome.posawesome.api.order_address.create_order_address",
			{
				customer: "CUST-1",
				delivery_charge: "Home Delivery",
				address: {
					address_line1: "1 High St",
					address_line2: "",
					city: "Leeds",
					county: "West Yorks",
					pincode: "LS1 1AA",
					country: "United Kingdom",
					phone: "0113",
					email_id: "",
				},
			},
			{ type: "POST" },
		);
		expect(onSaved).toHaveBeenCalledTimes(1);
		expect(onSaved.mock.calls[0][0]).toMatchObject({ name: "CUST-1-Shipping-ab12", created: true });
		expect(wrapper.find("[data-test='dhd-saved']").text()).toContain("Saved address");
		expect(wrapper.find("[data-test='dhd-error']").exists()).toBe(false);
	});

	it("shows the server's plain-text rejection inline and saves nothing", async () => {
		call.mockRejectedValue({
			_server_messages: JSON.stringify([JSON.stringify({ message: "Address must be plain text." })]),
		});
		const { wrapper, onSaved } = mountForm();
		await fill(wrapper, GOOD);
		await wrapper.find("[data-test='dhd-save']").trigger("click");
		await flushPromises();

		expect(wrapper.find("[data-test='dhd-error']").text()).toBe("Address must be plain text.");
		expect(wrapper.find("[data-test='dhd-saved']").exists()).toBe(false);
		expect(onSaved).not.toHaveBeenCalled();
	});

	it("refuses an invalid email without calling the server", async () => {
		const { wrapper } = mountForm();
		await fill(wrapper, { ...GOOD, "dhd-email": "nope" });
		await wrapper.find("[data-test='dhd-save']").trigger("click");
		await flushPromises();
		expect(call).not.toHaveBeenCalled();
		expect(wrapper.find("[data-test='dhd-error']").exists()).toBe(true);
	});
});

describe("PaymentAdditionalInfo DHD form", () => {
	beforeEach(() => {
		(globalThis as any).window.__ = (text: string) => text;
		(globalThis as any).window.frappe = { _: (text: string) => text };
	});

	const mountInfo = (props: Record<string, unknown>) =>
		mount(PaymentAdditionalInfo, {
			props: {
				invoiceDoc: { customer: "CUST-1" },
				posProfile: { posa_allow_sales_order: 1 },
				invoiceType: "Order",
				deliveryCharge: "Home Delivery",
				...props,
			},
			global: { mocks: { $frappe: { _: (t: string) => t } }, components, stubs: { VueDatePicker: true } },
		});

	it("shows the delivery address form only for a DHD charge", () => {
		expect(mountInfo({ showDhdAddressForm: true }).find("[data-test='dhd-address-form']").exists()).toBe(true);
		expect(mountInfo({ showDhdAddressForm: false }).find("[data-test='dhd-address-form']").exists()).toBe(
			false,
		);
	});

	it("re-emits the saved address to its parent", async () => {
		call.mockResolvedValue({ name: "ADDR-1", created: false });
		const onSaved = vi.fn();
		const wrapper = mountInfo({ showDhdAddressForm: true, onDhdAddressSaved: onSaved });
		await fill(wrapper, GOOD);
		await wrapper.find("[data-test='dhd-save']").trigger("click");
		await flushPromises();
		expect(onSaved).toHaveBeenCalledTimes(1);
		expect(onSaved.mock.calls[0][0].name).toBe("ADDR-1");
	});
});

describe("order address helpers", () => {
	it("identifies DHD by the order type name, not the id", () => {
		expect(isDhdCharge({ order_type_name: "DHD" })).toBe(true);
		expect(isDhdCharge({ order_type_name: "DDP" })).toBe(false);
		expect(isDhdCharge({})).toBe(false);
		expect(isDhdCharge(null)).toBe(false);
	});

	it("hides Add Customer Address for partners and store collection, keeps it for staff", () => {
		expect(canShowAddAddressAction(true, false)).toBe(false);
		expect(canShowAddAddressAction(false, true)).toBe(false);
		expect(canShowAddAddressAction(false, false)).toBe(true);
	});

	it("reads errors from server messages, plain messages, or falls back", () => {
		expect(orderAddressErrorMessage({ message: "frappe.exceptions.PermissionError: Not permitted" })).toBe(
			"Not permitted",
		);
		expect(orderAddressErrorMessage({}, "fallback")).toBe("fallback");
	});
});
