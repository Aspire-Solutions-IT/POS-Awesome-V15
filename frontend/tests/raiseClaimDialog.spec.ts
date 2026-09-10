// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

vi.mock("../src/posapp/services/api", () => ({
	default: { call: vi.fn() },
}));

const { toastShow } = vi.hoisted(() => ({ toastShow: vi.fn() }));
vi.mock("../src/posapp/stores/toastStore.js", () => ({
	useToastStore: () => ({ show: toastShow }),
}));

import RaiseClaimDialog from "../src/posapp/components/pos/claims/RaiseClaimDialog.vue";
import api from "../src/posapp/services/api";

/** Match frappe's __(): substitute {0}, {1}, … from the args array. */
const translate = (value: string, args?: any[]) =>
	Array.isArray(args)
		? value.replace(/\{(\d+)\}/g, (_match, index) => String(args[Number(index)] ?? ""))
		: value;

const flushPromises = async () => {
	await Promise.resolve();
	await Promise.resolve();
	await Promise.resolve();
	await new Promise((resolve) => setTimeout(resolve, 0));
};

const context = {
	customer: "CUST-1",
	company: "Test Company",
	currency: "GBP",
	items: [
		{ sales_order_item: "SOI-1", item_code: "ITEM-1", item_name: "Widget", qty: 3, uom: "Nos" },
		{ sales_order_item: "SOI-2", item_code: "ITEM-2", item_name: "Gadget", qty: 1, uom: "Nos" },
	],
	claim_types: [
		{ name: "Damage", claim_type_name: "Damage", evidence_required: 0, evidence_instructions: "" },
	],
	existing_claims: [],
	preferred_outcomes: ["Exchange", "Refund", "Credit", "Replace", "Service Call"],
	service_call_types: ["Maintenance Visit", "Spare Part"],
};

const BoxStub = defineComponent({
	setup: (_, { slots }) => () => h("div", {}, slots.default?.()),
});

const VBtnStub = defineComponent({
	props: { disabled: { type: Boolean, default: false }, loading: { type: Boolean, default: false } },
	emits: ["click"],
	setup: (props, { slots, emit }) => () =>
		h(
			"button",
			{ disabled: props.disabled || props.loading, onClick: () => emit("click") },
			slots.default?.(),
		),
});

const VTextFieldStub = defineComponent({
	props: { modelValue: { type: [String, Number], default: "" }, label: { type: String, default: "" } },
	emits: ["update:modelValue"],
	setup: (props, { emit }) => () =>
		h("input", {
			value: props.modelValue as any,
			"aria-label": props.label,
			onInput: (e: Event) => emit("update:modelValue", (e.target as HTMLInputElement).value),
		}),
});

const VTextareaStub = defineComponent({
	props: { modelValue: { type: String, default: "" }, label: { type: String, default: "" } },
	emits: ["update:modelValue"],
	setup: (props, { emit }) => () =>
		h("textarea", {
			value: props.modelValue,
			"aria-label": props.label,
			onInput: (e: Event) => emit("update:modelValue", (e.target as HTMLTextAreaElement).value),
		}),
});

const VCheckboxStub = defineComponent({
	props: { modelValue: { type: Boolean, default: false }, label: { type: String, default: "" } },
	emits: ["update:modelValue"],
	setup: (props, { emit }) => () =>
		h("input", {
			type: "checkbox",
			checked: props.modelValue,
			"aria-label": props.label,
			onChange: (e: Event) => emit("update:modelValue", (e.target as HTMLInputElement).checked),
		}),
});

const VSelectStub = defineComponent({
	props: {
		modelValue: { type: [String, Number], default: "" },
		items: { type: Array, default: () => [] },
		itemTitle: { type: String, default: "title" },
		itemValue: { type: String, default: "value" },
		label: { type: String, default: "" },
	},
	emits: ["update:modelValue"],
	setup: (props, { emit }) => {
		const val = (item: any) =>
			item && typeof item === "object" ? String(item[props.itemValue] ?? "") : String(item ?? "");
		const lab = (item: any) =>
			item && typeof item === "object" ? String(item[props.itemTitle] ?? "") : String(item ?? "");
		return () =>
			h(
				"select",
				{
					value: props.modelValue as any,
					"aria-label": props.label,
					onChange: (e: Event) => emit("update:modelValue", (e.target as HTMLSelectElement).value),
				},
				(props.items as any[]).map((item) => h("option", { value: val(item) }, lab(item))),
			);
	},
});

const mountDialog = (props: Record<string, any> = {}) =>
	mount(RaiseClaimDialog, {
		props: { modelValue: true, salesOrder: "SO-1", customerName: "Test Customer", ...props },
		global: {
			mocks: { __: translate },
			stubs: { transition: false },
			components: {
				VDialog: BoxStub,
				VCard: BoxStub,
				VCardTitle: BoxStub,
				VCardText: BoxStub,
				VCardActions: BoxStub,
				VRow: BoxStub,
				VCol: BoxStub,
				VAlert: BoxStub,
				VTable: BoxStub,
				VFileInput: BoxStub,
				VBtn: VBtnStub,
				VTextField: VTextFieldStub,
				VTextarea: VTextareaStub,
				VCheckbox: VCheckboxStub,
				VSelect: VSelectStub,
			},
		},
	});

describe("RaiseClaimDialog", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.clearAllMocks();
		vi.stubGlobal("__", translate);
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("get_sales_order_claim_context")) return context;
			if (method.endsWith("raise_claim")) return { name: "CLM-0001", workflow_state: "Pending Approval" };
			return null;
		});
	});

	it("loads the order context when opened", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		expect(api.call).toHaveBeenCalledWith(
			"posawesome.posawesome.api.claims.get_sales_order_claim_context",
			{ sales_order: "SO-1" },
		);
		expect(wrapper.text()).toContain("ITEM-1");
		expect(wrapper.text()).toContain("Gadget");
	});

	it("submits only the ticked items and emits created", async () => {
		const onCreated = vi.fn();
		const onClose = vi.fn();
		const wrapper = mountDialog({ onCreated, "onUpdate:modelValue": onClose });
		await flushPromises();

		// claim type auto-selected (only one); pick an outcome and describe the fault
		await wrapper.find("select[aria-label='Preferred outcome']").setValue("Replace");
		await wrapper.find("textarea[aria-label='What is wrong?']").setValue("Arrived cracked");

		// tick the first item only
		const checkboxes = wrapper.findAll("input[type='checkbox']");
		await checkboxes[0].setValue(true);
		await flushPromises();

		const submit = wrapper.findAll("button").find((b) => b.text() === "Submit for review")!;
		expect(submit.attributes("disabled")).toBeUndefined();
		await submit.trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) => c[0].endsWith("raise_claim"));
		expect(call).toBeTruthy();
		expect(call[1].payload).toMatchObject({
			sales_order: "SO-1",
			claim_type: "Damage",
			preferred_outcome: "Replace",
			description: "Arrived cracked",
			items: [{ sales_order_item: "SOI-1", qty: 3 }],
		});
		expect(onCreated).toHaveBeenCalledWith("CLM-0001");
		expect(onClose).toHaveBeenCalledWith(false);
		expect(toastShow).toHaveBeenCalled();
	});

	it("keeps submit disabled until an item is selected", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("select[aria-label='Preferred outcome']").setValue("Refund");
		await wrapper.find("textarea[aria-label='What is wrong?']").setValue("Faulty");
		await flushPromises();
		const submit = wrapper.findAll("button").find((b) => b.text() === "Submit for review")!;
		expect(submit.attributes("disabled")).toBeDefined();
	});

	it("warns when a selected item is already on an open claim", async () => {
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("get_sales_order_claim_context")) {
				return {
					...context,
					existing_claims: [
						{
							name: "CLM-0009",
							workflow_state: "Pending Approval",
							items: [{ sales_order_item: "SOI-1", item_code: "ITEM-1", qty: 1 }],
						},
					],
				};
			}
			return null;
		});
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.findAll("input[type='checkbox']")[0].setValue(true);
		await flushPromises();
		expect(wrapper.text()).toContain("already on an open claim");
		expect(wrapper.text()).toContain("CLM-0009");
	});

	it("blocks submit when the claim type requires evidence and none is attached", async () => {
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("get_sales_order_claim_context")) {
				return {
					...context,
					claim_types: [
						{
							name: "Damage",
							claim_type_name: "Damage",
							evidence_required: 1,
							evidence_instructions: "Photograph the damage from two angles.",
						},
					],
				};
			}
			return null;
		});
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("select[aria-label='Preferred outcome']").setValue("Replace");
		await wrapper.find("textarea[aria-label='What is wrong?']").setValue("Cracked");
		await wrapper.findAll("input[type='checkbox']")[0].setValue(true);
		await flushPromises();

		expect(wrapper.text()).toContain("Photograph the damage from two angles.");
		const submit = wrapper.findAll("button").find((b) => b.text() === "Submit for review")!;
		expect(submit.attributes("disabled")).toBeDefined();
	});
});
