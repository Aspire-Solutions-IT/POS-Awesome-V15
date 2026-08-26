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

vi.mock("../src/posapp/components/pos/items/ItemsSelector.vue", async () => {
	const { defineComponent, h } = await import("vue");
	return {
		default: defineComponent({
			name: "ItemsSelectorStub",
			emits: ["add-item"],
			setup(_props, { emit }) {
				return () =>
					h(
						"button",
						{
							class: "stub-add-item",
							onClick: () => emit("add-item", { item_code: "ITEM-NEW", stock_uom: "Nos" }),
						},
						"stub add",
					);
			},
		}),
	};
});

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

const newItemDetails = {
	item_code: "ITEM-NEW",
	item_name: "Newly Added Item",
	description: "Added from the item selector",
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
	rate: 42.5,
	currency: "GBP",
	delivery_date: "2026-07-30",
};

/** Preview result for an edit that does not raise the total. */
const noIncreasePreview = {
	current_grand_total: 100,
	projected_grand_total: 100,
	difference: 0,
	advance_paid: 100,
	amount_due: 0,
	credit_after_change: 0,
	currency: "GBP",
	customer_credit: { unallocated_payments: 0, stored_value: 0, total: 0 },
};

/** Preview result for an edit that raises the total and must be paid for. */
const increasePreview = {
	...noIncreasePreview,
	projected_grand_total: 155,
	difference: 55,
	amount_due: 55,
	customer_credit: { unallocated_payments: 40, stored_value: 0, total: 40 },
};

/** Mock the read calls the page makes on mount, plus anything the test adds. */
const mockApi = (extra: (_method: string, _args: any) => any = () => undefined) => {
	(api.call as any).mockImplementation(async (method: string, args: any) => {
		const handled = extra(method, args);
		if (handled !== undefined) return handled;
		if (method.endsWith("get_managed_sales_orders")) {
			return [{ name: "SO-1", customer_name: "Test Customer", currency: "GBP" }];
		}
		if (method.endsWith("get_managed_sales_order")) {
			return baseDetail;
		}
		if (method.endsWith("get_managed_sales_order_new_item_details")) {
			return newItemDetails;
		}
		if (method.endsWith("preview_managed_sales_order_items")) {
			return noIncreasePreview;
		}
		return null;
	});
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
			// A mode of payment must exist or the payment dialog cannot be confirmed.
			payments: [{ mode_of_payment: "Cash" }],
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
					VNavigationDrawer: BoxStub,
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

	/** Open the picker and stage one item through it. */
	const addItemThroughSelector = async (wrapper: any) => {
		const addButton = wrapper
			.findAll("button")
			.find((button: any) => button.text().trim() === "Add Items");
		expect(addButton).toBeTruthy();
		await addButton!.trigger("click");

		// The selector is an async component, so its module resolution needs more than
		// a single flush before it appears in the tree.
		for (let attempt = 0; attempt < 10; attempt += 1) {
			await flushPromises();
			if (wrapper.find("button.stub-add-item").exists()) break;
		}

		const stubAdd = wrapper.find("button.stub-add-item");
		expect(stubAdd.exists()).toBe(true);
		await stubAdd.trigger("click");
		await flushPromises();
	};

	const findSaveButton = (wrapper: any) =>
		wrapper.findAll("button").find((button: any) => button.text().trim() === "Save");

	it("prices an added item through the server and stages it as a new row", async () => {
		mockApi();

		const wrapper = mountView();
		await flushPromises();
		await addItemThroughSelector(wrapper);

		const pricingCall = (api.call as any).mock.calls.find(
			(call: any[]) =>
				call[0] ===
				"posawesome.posawesome.api.sales_orders.get_managed_sales_order_new_item_details",
		);
		expect(pricingCall).toBeTruthy();
		expect(pricingCall[1]).toEqual({
			sales_order: "SO-1",
			item_code: "ITEM-NEW",
			uom: "Nos",
		});

		expect(wrapper.text()).toContain("Newly Added Item");
		expect(wrapper.text()).toContain("New");

		// One rate input, on the staged row only: saved rows keep their price.
		const rateInputs = wrapper
			.findAll("input.items-input")
			.filter((input: any) => input.attributes("min") === "0");
		expect(rateInputs).toHaveLength(1);
		expect((rateInputs[0]!.element as HTMLInputElement).value).toBe("42.5");
	});

	it("sends staged rows with a null docname and a rate, and saved rows without one", async () => {
		mockApi((method) => {
			if (method.endsWith("update_managed_sales_order_items")) return baseDetail;
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();
		await addItemThroughSelector(wrapper);

		const rateInput = wrapper
			.findAll("input.items-input")
			.find((input: any) => input.attributes("min") === "0");
		await rateInput!.setValue("55");

		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		const updateItemsCall = (api.call as any).mock.calls.find(
			(call: any[]) =>
				call[0] === "posawesome.posawesome.api.sales_orders.update_managed_sales_order_items",
		);
		expect(updateItemsCall).toBeTruthy();

		const rows = updateItemsCall[1].data.items;
		expect(rows).toHaveLength(3);
		for (const row of rows.slice(0, 2)) {
			expect(row.docname).toBeTruthy();
			expect(row).not.toHaveProperty("rate");
		}
		expect(rows[2]).toEqual(
			expect.objectContaining({
				docname: null,
				item_code: "ITEM-NEW",
				uom: "Nos",
				description: "Added from the item selector",
				qty: 1,
				rate: 55,
			}),
		);
	});

	it("stops reporting changes once a staged row is removed again", async () => {
		mockApi();

		const wrapper = mountView();
		await flushPromises();
		expect(findSaveButton(wrapper)!.attributes("disabled")).toBeDefined();

		await addItemThroughSelector(wrapper);
		expect(findSaveButton(wrapper)!.attributes("disabled")).toBeUndefined();

		// The staged row is last, and saved rows must not be left looking dirty.
		const removeButtons = wrapper
			.findAll("button")
			.filter((button: any) => button.text().trim() === "Remove");
		expect(removeButtons).toHaveLength(3);
		await removeButtons[2]!.trigger("click");
		await flushPromises();

		expect(findSaveButton(wrapper)!.attributes("disabled")).toBeDefined();
	});

	it("asks for payment instead of saving when the change raises the total", async () => {
		mockApi((method) => {
			if (method.endsWith("preview_managed_sales_order_items")) return increasePreview;
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();
		await addItemThroughSelector(wrapper);
		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		// Nothing may be written until the money is taken.
		const saved = (api.call as any).mock.calls.find((call: any[]) =>
			call[0].endsWith("update_managed_sales_order_items"),
		);
		expect(saved).toBeFalsy();
		expect(wrapper.text()).toContain("Payment Required");
		expect(wrapper.text()).toContain("Amount Due Now");
		// advance_paid cannot see money sitting on the customer's account.
		expect(wrapper.text()).toContain("Customer already holds");
	});

	it("saves nothing when the payment is cancelled", async () => {
		mockApi((method) => {
			if (method.endsWith("preview_managed_sales_order_items")) return increasePreview;
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();
		await addItemThroughSelector(wrapper);
		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		const cancel = wrapper.findAll("button").find((b: any) => b.text().trim() === "Cancel");
		expect(cancel).toBeTruthy();
		await cancel!.trigger("click");
		await flushPromises();

		const wrote = (api.call as any).mock.calls.some(
			(call: any[]) =>
				call[0].endsWith("update_managed_sales_order_items") ||
				call[0].endsWith("update_managed_sales_order_items_with_payment"),
		);
		expect(wrote).toBe(false);
		// The edit is still staged, so Save stays enabled.
		expect(findSaveButton(wrapper)!.attributes("disabled")).toBeUndefined();
	});

	it("applies items and payment in a single call once confirmed", async () => {
		mockApi((method) => {
			if (method.endsWith("preview_managed_sales_order_items")) return increasePreview;
			if (method.endsWith("update_managed_sales_order_items_with_payment")) {
				return { sales_order: baseDetail, payment_entry: "PE-1", amount_paid: 55 };
			}
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();
		await addItemThroughSelector(wrapper);
		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		const confirm = wrapper
			.findAll("button")
			.find((b: any) => b.text().trim() === "Take Payment and Save");
		expect(confirm).toBeTruthy();
		await confirm!.trigger("click");
		await flushPromises();

		const payCall = (api.call as any).mock.calls.find((call: any[]) =>
			call[0].endsWith("update_managed_sales_order_items_with_payment"),
		);
		expect(payCall).toBeTruthy();
		expect(payCall[1].data.items).toHaveLength(3);
		// Guards against the total shifting while the dialog was open.
		expect(payCall[1].data.payment.expected_amount).toBe(55);
		// Items must not also go through the plain save path.
		const plain = (api.call as any).mock.calls.filter(
			(call: any[]) => call[0].endsWith("update_managed_sales_order_items"),
		);
		expect(plain).toHaveLength(0);
	});

	it("blocks item editing while a Pick List is active on the whole order", async () => {
		mockApi((method) => {
			if (method.endsWith("get_managed_sales_order")) {
				return {
					...baseDetail,
					order_level_lock: {
						is_locked: true,
						reason: "Linked Pick Lists block editing: PICK-1 (Open)",
					},
				};
			}
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("Linked Pick Lists block editing: PICK-1 (Open)");
		const addButton = wrapper
			.findAll("button")
			.find((button: any) => button.text().trim() === "Add Items");
		expect(addButton!.attributes("disabled")).toBeDefined();
	});
});
