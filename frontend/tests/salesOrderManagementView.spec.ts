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

/** What the stubbed selector emits; a test can point it at another item. */
const selectorItem: { current: Record<string, any> } = {
	current: { item_code: "ITEM-NEW", stock_uom: "Nos" },
};

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
							onClick: () => emit("add-item", { ...selectorItem.current }),
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

/** Renders its slot only when open, like a real v-dialog. */
const VDialogStub = defineComponent({
	props: { modelValue: { type: Boolean, default: false } },
	setup(props, { slots }) {
		return () => (props.modelValue ? h("div", {}, slots.default?.()) : null);
	},
});

const VCheckboxStub = defineComponent({
	props: {
		modelValue: { type: Boolean, default: false },
		label: { type: String, default: "" },
	},
	emits: ["update:modelValue"],
	setup(props, { emit }) {
		return () =>
			h("label", {}, [
				h("input", {
					type: "checkbox",
					checked: props.modelValue,
					onChange: (event: Event) =>
						emit("update:modelValue", (event.target as HTMLInputElement).checked),
				}),
				props.label,
			]);
	},
});

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

/** Renders as a real <select> so a test can pick an option, unlike the box stubs. */
const VSelectStub = defineComponent({
	props: {
		modelValue: { type: [String, Number], default: "" },
		items: { type: Array, default: () => [] },
		itemTitle: { type: String, default: "title" },
		itemValue: { type: String, default: "value" },
		label: { type: String, default: "" },
	},
	emits: ["update:modelValue"],
	setup(props, { emit }) {
		const optionValue = (item: any) =>
			item && typeof item === "object" ? String(item[props.itemValue] ?? "") : String(item ?? "");
		const optionLabel = (item: any) =>
			item && typeof item === "object" ? String(item[props.itemTitle] ?? "") : String(item ?? "");
		return () =>
			h(
				"select",
				{
					value: props.modelValue as any,
					"aria-label": props.label,
					onChange: (event: Event) =>
						emit("update:modelValue", (event.target as HTMLSelectElement).value),
				},
				(props.items as any[]).map((item) =>
					h("option", { value: optionValue(item) }, optionLabel(item)),
				),
			);
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

/** An order whose POS Profile has an NS warehouse, as a real POS order does. */
const nsDetail = {
	...baseDetail,
	company: "Test Company",
	pos_profile: "Main POS",
	default_ns_warehouse: "NS Main - TC",
	delivery_charge_collection: 0,
};

const nsWarehouseRows = [
	{ name: "NS Main - TC", warehouse_name: "NS Main" },
	{ name: "NS Annexe - TC", warehouse_name: "NS Annexe" },
];

const nsItemDetails = {
	item_code: "NS-1001",
	item_name: "NS Sofa",
	description: "Added from the item selector",
	uom: "Nos",
	stock_uom: "Nos",
	conversion_factor: 1,
	rate: 99,
	currency: "GBP",
	delivery_date: "2026-07-30",
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
	credit_applicable: 40,
};

/** Customer holds more than the increase, so credit covers the whole thing. */
const fullyCoveredPreview = {
	...increasePreview,
	amount_due: 30,
	customer_credit: { unallocated_payments: 250, stored_value: 0, total: 250 },
	credit_applicable: 30,
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
		if (method === "frappe.client.get_list") {
			return nsWarehouseRows;
		}
		return null;
	});
};

describe("SalesOrderManagementView", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.clearAllMocks();
		selectorItem.current = { item_code: "ITEM-NEW", stock_uom: "Nos" };
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
		// clearAllMocks wipes calls but not implementations, so without this a test
		// inherits whatever the previous one stubbed.
		mockApi();
	});

	const mountView = (overrides: Record<string, any> = {}) =>
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
					VDialog: VDialogStub,
					VCheckbox: VCheckboxStub,
					VSelect: BoxStub,
					VueDatePicker: VueDatePickerStub,
					VNavigationDrawer: BoxStub,
					...overrides,
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
		expect(wrapper.text()).toContain("To Take Now");
		// advance_paid cannot see money on the customer's account, so it is offered here.
		expect(wrapper.text()).toContain("of the customer");
		expect(wrapper.text()).toContain("credit");
	});

	it("offers the customer's credit but does not apply it unasked", async () => {
		mockApi((method) => {
			if (method.endsWith("preview_managed_sales_order_items")) return increasePreview;
			if (method.endsWith("update_managed_sales_order_items_with_payment")) {
				return { sales_order: baseDetail, payment_entry: "PE-1", amount_paid: 55, credit_applied: 0 };
			}
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();
		await addItemThroughSelector(wrapper);
		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		expect(wrapper.text()).toContain("credit");
		const confirm = wrapper
			.findAll("button")
			.find((b: any) => b.text().trim() === "Take Payment and Save");
		await confirm!.trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) =>
			c[0].endsWith("update_managed_sales_order_items_with_payment"),
		);
		// Unticked: the customer's money must not be spent without being chosen.
		expect(call[1].data.payment.use_credit).toBe(0);
	});

	it("sends the credit flag once the cashier ticks it", async () => {
		mockApi((method) => {
			if (method.endsWith("preview_managed_sales_order_items")) return fullyCoveredPreview;
			if (method.endsWith("update_managed_sales_order_items_with_payment")) {
				return { sales_order: baseDetail, payment_entry: null, amount_paid: 0, credit_applied: 30 };
			}
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();
		await addItemThroughSelector(wrapper);
		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		const checkbox = wrapper.find('input[type="checkbox"]');
		expect(checkbox.exists()).toBe(true);
		await checkbox.setValue(true);

		// Credit covers it all, so the till takes nothing and the wording changes.
		const confirm = wrapper
			.findAll("button")
			.find((b: any) => b.text().trim() === "Apply Credit and Save");
		expect(confirm).toBeTruthy();
		await confirm!.trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) =>
			c[0].endsWith("update_managed_sales_order_items_with_payment"),
		);
		expect(call[1].data.payment.use_credit).toBe(1);
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

	it("reports surplus that could not be moved automatically", async () => {
		mockApi((method) => {
			if (method.endsWith("get_managed_sales_order")) {
				return {
					...baseDetail,
					surplus: {
						amount: 739.99,
						reason:
							"This surplus is not linked to a payment on this order and needs manual reconciliation.",
					},
				};
			}
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("could not be moved automatically");
		expect(wrapper.text()).toContain("needs manual reconciliation");
		// Settling is automatic now - there is nothing for the cashier to press.
		const release = wrapper
			.findAll("button")
			.find((b: any) => b.text().trim() === "Release to account");
		expect(release).toBeFalsy();
	});

	it("says nothing about surplus on an ordinary order", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).not.toContain("could not be moved automatically");
	});

	it("locks every control once the order is fully picked", async () => {
		mockApi((method) => {
			if (method.endsWith("get_managed_sales_order")) {
				return {
					...baseDetail,
					order_level_lock: {
						is_locked: true,
						reason: "This Sales Order has been fully picked and can no longer be edited.",
					},
				};
			}
			return undefined;
		});

		const wrapper = mountView();
		await flushPromises();

		expect(wrapper.text()).toContain("fully picked and can no longer be edited");

		const addButton = wrapper
			.findAll("button")
			.find((b: any) => b.text().trim() === "Add Items");
		expect(addButton!.attributes("disabled")).toBeDefined();

		// The unlocked row must be read only too - a finished order is closed outright.
		const qtyInputs = wrapper
			.findAll("input.items-input")
			.filter((i: any) => i.attributes("min") === "0.01");
		expect(qtyInputs.length).toBeGreaterThan(0);
		for (const input of qtyInputs) {
			expect(input.attributes("readonly")).toBeDefined();
		}

		const removeButtons = wrapper
			.findAll("button")
			.filter((b: any) => b.text().trim() === "Remove");
		for (const button of removeButtons) {
			expect(button.attributes("disabled")).toBeDefined();
		}
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
	/** An NS order, with a picker that a test can actually operate. */
	const mountNsView = async (detail: Record<string, any> = nsDetail) => {
		selectorItem.current = { item_code: "NS-1001", stock_uom: "Nos" };
		mockApi((method) => {
			if (method.endsWith("get_managed_sales_order_new_item_details")) return nsItemDetails;
			if (method.endsWith("update_managed_sales_order_items")) return detail;
			if (method.endsWith("get_managed_sales_order")) return detail;
			return undefined;
		});
		const wrapper = mountView({ VSelect: VSelectStub });
		await flushPromises();
		return wrapper;
	};

	const warehouseSelects = (wrapper: any) => wrapper.findAll("select.item-warehouse-select");

	const warehouseValues = (wrapper: any) =>
		warehouseSelects(wrapper).map((select: any) => (select.element as HTMLSelectElement).value);

	const savedItemsPayload = () =>
		(api.call as any).mock.calls.find(
			(call: any[]) =>
				call[0] === "posawesome.posawesome.api.sales_orders.update_managed_sales_order_items",
		)?.[1]?.data?.items;

	it("stages a new NS row in the order's default NS warehouse and sends it on save", async () => {
		const wrapper = await mountNsView();
		await addItemThroughSelector(wrapper);

		const listCall = (api.call as any).mock.calls.find(
			(call: any[]) => call[0] === "frappe.client.get_list",
		);
		expect(listCall).toBeTruthy();
		expect(listCall[1]).toEqual(
			expect.objectContaining({
				doctype: "Warehouse",
				filters: { is_group: 0, is_ns_location: 1, company: "Test Company" },
			}),
		);

		// One picker: on the staged NS row, not on the saved rows.
		expect(warehouseValues(wrapper)).toEqual(["NS Main - TC"]);

		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		expect(savedItemsPayload()).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ docname: null, item_code: "NS-1001", warehouse: "NS Main - TC" }),
			]),
		);
	});

	it("offers no picker on an NS row already saved on the order", async () => {
		const wrapper = await mountNsView({
			...nsDetail,
			items: [
				{
					...baseDetail.items[1],
					name: "SOI-NS",
					item_code: "NS-2002",
					item_name: "Saved NS Item",
					warehouse: "NS Annexe - TC",
				},
			],
		});

		expect(warehouseSelects(wrapper)).toHaveLength(0);
	});

	it("hides the picker on a Collection order, as the cart does", async () => {
		const wrapper = await mountNsView({ ...nsDetail, delivery_charge_collection: 1 });
		await addItemThroughSelector(wrapper);

		expect(warehouseSelects(wrapper)).toHaveLength(0);

		// The row still goes to the default NS warehouse; only the choice is withheld.
		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();
		expect(savedItemsPayload()).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ item_code: "NS-1001", warehouse: "NS Main - TC" }),
			]),
		);
	});

	it("keeps the picker on a Collection order at Peterborough", async () => {
		const wrapper = await mountNsView({
			...nsDetail,
			delivery_charge_collection: 1,
			pos_profile: "Peterborough",
		});
		await addItemThroughSelector(wrapper);

		expect(warehouseSelects(wrapper)).toHaveLength(1);
	});

	it("re-adding an NS item whose warehouse was changed stages a second row", async () => {
		const wrapper = await mountNsView();
		await addItemThroughSelector(wrapper);

		await warehouseSelects(wrapper)[0]!.setValue("NS Annexe - TC");
		await addItemThroughSelector(wrapper);

		// Two separate lines, not one line of qty 2.
		expect(warehouseValues(wrapper)).toEqual(["NS Annexe - TC", "NS Main - TC"]);

		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		const staged = (savedItemsPayload() || []).filter((row: any) => row.item_code === "NS-1001");
		expect(staged).toHaveLength(2);
		expect(staged.map((row: any) => row.warehouse)).toEqual(["NS Annexe - TC", "NS Main - TC"]);
		expect(staged.every((row: any) => row.qty === 1)).toBe(true);
	});

	it("still merges a re-added NS item that is going to the same warehouse", async () => {
		const wrapper = await mountNsView();
		await addItemThroughSelector(wrapper);
		await addItemThroughSelector(wrapper);

		expect(warehouseValues(wrapper)).toEqual(["NS Main - TC"]);

		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		const staged = (savedItemsPayload() || []).filter((row: any) => row.item_code === "NS-1001");
		expect(staged).toHaveLength(1);
		expect(staged[0].qty).toBe(2);
	});

	it("blocks the save when the warehouse is cleared on a staged NS row", async () => {
		const wrapper = await mountNsView();
		await addItemThroughSelector(wrapper);

		await warehouseSelects(wrapper)[0]!.setValue("");
		await findSaveButton(wrapper)!.trigger("click");
		await flushPromises();

		expect(wrapper.text()).toContain("please choose a warehouse");
		expect(savedItemsPayload()).toBeUndefined();
	});
});
