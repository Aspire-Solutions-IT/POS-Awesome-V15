// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

vi.mock("../src/posapp/services/api", () => ({
	default: {
		call: vi.fn(),
	},
}));

vi.mock("../src/posapp/stores/toastStore.js", () => ({
	useToastStore: () => ({
		show: vi.fn(),
	}),
}));

import SalesOrderManagementView from "../src/posapp/components/pos/shell/SalesOrderManagementView.vue";
import api from "../src/posapp/services/api";
import { useUIStore } from "../src/posapp/stores/uiStore";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});

const VBtnStub = defineComponent({
	props: {
		disabled: { type: Boolean, default: false },
		loading: { type: Boolean, default: false },
	},
	emits: ["click"],
	setup(props, { slots, emit }) {
		return () =>
			h(
				"button",
				{
					disabled: props.disabled || props.loading,
					onClick: () => emit("click"),
				},
				slots.default?.(),
			);
	},
});

const VTextFieldStub = defineComponent({
	props: {
		modelValue: { type: [String, Number], default: "" },
		label: { type: String, default: "" },
	},
	emits: ["update:modelValue", "keyup.enter"],
	setup(props, { emit }) {
		return () =>
			h("input", {
				value: props.modelValue as any,
				"aria-label": props.label,
				onInput: (event: Event) =>
					emit("update:modelValue", (event.target as HTMLInputElement).value),
			});
	},
});

const VTextareaStub = defineComponent({
	props: {
		modelValue: { type: String, default: "" },
		label: { type: String, default: "" },
	},
	emits: ["update:modelValue"],
	setup(props, { emit }) {
		return () =>
			h("textarea", {
				value: props.modelValue,
				"aria-label": props.label,
				onInput: (event: Event) =>
					emit("update:modelValue", (event.target as HTMLTextAreaElement).value),
			});
	},
});

const VueDatePickerStub = defineComponent({
	props: {
		modelValue: { type: String, default: "" },
	},
	emits: ["update:modelValue"],
	setup(props, { emit }) {
		return () =>
			h("input", {
				type: "date",
				value: props.modelValue,
				onInput: (event: Event) =>
					emit("update:modelValue", (event.target as HTMLInputElement).value),
			});
	},
});

const flushPromises = async () => {
	await Promise.resolve();
	await Promise.resolve();
	await Promise.resolve();
	await new Promise((resolve) => setTimeout(resolve, 0));
};

const baseDetail = {
	name: "SO-1",
	customer: "CUST-1",
	customer_name: "Test Customer",
	status: "To Deliver",
	transaction_date: "2026-07-27",
	prefered_earliest_delivery_date: "2026-07-30",
	customer_ref: "REF-1",
	customer_order_ref: "PO-1",
	currency: "GBP",
	grand_total: 100,
	rounded_total: 100,
	advance_paid: 0,
	outstanding_balance: 100,
	items: [
		{
			name: "SOI-LOCKED",
			item_code: "ITEM-LOCKED",
			item_name: "Locked Item",
			description: "Locked row",
			warehouse: "Main - TC",
			uom: "Nos",
			qty: 1,
			picked_qty: 1,
			delivered_qty: 0,
			rate: 10,
			conversion_factor: 1,
			delivery_date: "2026-07-28",
			component_due_date: "2026-07-29",
			is_locked: true,
			lock_reason: "Picked qty is greater than 0.",
			linked_pick_lists: [],
		},
		{
			name: "SOI-OPEN",
			item_code: "ITEM-OPEN",
			item_name: "Editable Item",
			description: "Editable row",
			warehouse: "Main - TC",
			uom: "Nos",
			qty: 2,
			picked_qty: 0,
			delivered_qty: 0,
			rate: 20,
			conversion_factor: 1,
			delivery_date: "2026-07-30",
			component_due_date: "2026-08-02",
			is_locked: false,
			lock_reason: null,
			linked_pick_lists: [],
		},
	],
};

describe("SalesOrderManagementView", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.clearAllMocks();
		vi.stubGlobal("__", (value: string) => value);
		(globalThis as any).frappe = { _: (value: string) => value };
		const uiStore = useUIStore();
		uiStore.setPosProfile({
			name: "Main POS",
			company: "Test Company",
			currency: "GBP",
			custom_allow_select_sales_order: 1,
			payments: [],
		} as any);
	});

	const mountView = () =>
		mount(SalesOrderManagementView, {
			global: {
				mocks: {
					__: (value: string) => value,
				},
				components: {
					VContainer: BoxStub,
					VRow: BoxStub,
					VCol: BoxStub,
					VCard: BoxStub,
					VCardTitle: BoxStub,
					VCardText: BoxStub,
					VCardActions: BoxStub,
					VAlert: BoxStub,
					VBtn: VBtnStub,
					VTextField: VTextFieldStub,
					VTextarea: VTextareaStub,
					VTable: BoxStub,
					VDialog: BoxStub,
					VSelect: BoxStub,
					VueDatePicker: VueDatePickerStub,
				},
			},
		});

	it("renders locked and editable rows distinctly", async () => {
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("get_managed_sales_orders")) {
				return [{ name: "SO-1", customer_name: "Test Customer", currency: "GBP" }];
			}
			if (method.endsWith("get_managed_sales_order")) {
				return baseDetail;
			}
			return null;
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("Locked");
		expect(wrapper.text()).toContain("Editable");
		expect(wrapper.text()).toContain("Picked qty is greater than 0.");

		const removeButtons = wrapper
			.findAll("button")
			.filter((button) => button.text().trim() === "Remove");
		expect(removeButtons).toHaveLength(2);
		expect(removeButtons[0]?.attributes("disabled")).toBeDefined();
		expect(removeButtons[1]?.attributes("disabled")).toBeUndefined();
	});

	it("submits unlocked item edits through the managed items API", async () => {
		(api.call as any).mockImplementation(async (method: string, args: any) => {
			if (method.endsWith("get_managed_sales_orders")) {
				return [{ name: "SO-1", customer_name: "Test Customer", currency: "GBP" }];
			}
			if (method.endsWith("get_managed_sales_order")) {
				return baseDetail;
			}
			if (method.endsWith("update_managed_sales_order_items")) {
				return {
					...baseDetail,
					items: [
						baseDetail.items[0],
						{
							...baseDetail.items[1],
							qty: args.data.items[1].qty,
						},
					],
				};
			}
			return baseDetail;
		});

		const wrapper = mountView();
		await flushPromises();

		const numberInputs = wrapper
			.findAll("input.items-input")
			.filter((input) => input.attributes("type") === "number");
		const editableQtyInput = numberInputs[1];
		expect(editableQtyInput).toBeTruthy();
		await editableQtyInput!.setValue("3");

		const saveButton = wrapper
			.findAll("button")
			.find((button) => button.text().trim() === "Save");
		expect(saveButton).toBeTruthy();
		await saveButton!.trigger("click");
		await flushPromises();

		const updateItemsCall = (api.call as any).mock.calls.find(
			(call: any[]) => call[0] === "posawesome.posawesome.api.sales_orders.update_managed_sales_order_items",
		);
		expect(updateItemsCall).toBeTruthy();
		expect(updateItemsCall[1].data.name).toBe("SO-1");
		expect(updateItemsCall[1].data.items).toEqual(
			expect.arrayContaining([expect.objectContaining({ docname: "SOI-OPEN", qty: 3 })]),
		);
		expect(updateItemsCall[1].data.items[0]).not.toHaveProperty("rate");
		expect(updateItemsCall[1].data.items[0]).not.toHaveProperty("warehouse");
		expect(updateItemsCall[1].data.items[0]).not.toHaveProperty("delivery_date");
	});
});
