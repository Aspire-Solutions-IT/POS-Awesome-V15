// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

vi.mock("../src/posapp/services/api", () => ({
	default: { call: vi.fn() },
}));

// Stands in for the real picker, which needs the full POS app around it. Each
// button emits add-item with that item, as ItemsSelector does outside the cart.
vi.mock("../src/posapp/components/pos/items/ItemsSelector.vue", async () => {
	const { defineComponent, h } = await import("vue");
	const items = [
		{ item_code: "SOFA-NEW", item_name: "New Sofa" },
		{ item_code: "CHAIR-TPL", item_name: "Chair Template", has_variants: 1 },
	];
	return {
		default: defineComponent({
			props: { context: { type: String, default: "" } },
			emits: ["add-item"],
			setup: (props, { emit }) => () =>
				h(
					"div",
					{ class: "items-selector-stub", "data-context": props.context },
					items.map((item) =>
						h("button", { class: `pick-${item.item_code}`, onClick: () => emit("add-item", item) }, item.item_code),
					),
				),
		}),
	};
});

import ProposeDecisionDialog from "../src/posapp/components/pos/claims/ProposeDecisionDialog.vue";
import api from "../src/posapp/services/api";

const translate = (value: string, args?: any[]) =>
	Array.isArray(args)
		? value.replace(/\{(\d+)\}/g, (_m, i) => String(args[Number(i)] ?? ""))
		: value;

const flushPromises = async () => {
	await Promise.resolve();
	await Promise.resolve();
	await Promise.resolve();
	await new Promise((resolve) => setTimeout(resolve, 0));
};

const claim = {
	name: "CLM-0001",
	currency: "GBP",
	preferred_outcome: "Replace",
	items: [
		{ name: "CCI-1", item_code: "ITEM-1", item_name: "Widget", qty: 2 },
		{ name: "CCI-2", item_code: "ITEM-2", item_name: "Gadget", qty: 1 },
	],
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
	mount(ProposeDecisionDialog, {
		props: { modelValue: true, claim, ...props },
		global: {
			mocks: { __: translate },
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
				VBtn: VBtnStub,
				VTextField: VTextFieldStub,
				VTextarea: VTextareaStub,
				VCheckbox: VCheckboxStub,
				VSelect: VSelectStub,
			},
		},
	});

const recordButton = (wrapper: ReturnType<typeof mountDialog>) =>
	wrapper.findAll("button").find((b) => b.text() === "Record decision")!;

const tickItem = async (wrapper: ReturnType<typeof mountDialog>, label: string) => {
	const checkbox = wrapper
		.findAll("input[type='checkbox']")
		.find((c) => c.attributes("aria-label") === label)!;
	await checkbox.setValue(true);
};

describe("ProposeDecisionDialog", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		vi.stubGlobal("__", translate);
		(api.call as any).mockImplementation(async () => ({ name: "CCD-0001", workflow_state: "Approved" }));
	});

	it("defaults the outcome to the claim's preferred outcome", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		const select = wrapper.find("select[aria-label='Suggested outcome']")
			.element as HTMLSelectElement;
		expect(select.value).toBe("Replace");
	});

	it("requires a replacement item on every selected line for Replace", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		await tickItem(wrapper, "Include ITEM-1");
		await flushPromises();
		expect(recordButton(wrapper).attributes("disabled")).toBeDefined();
	});

	it("requires a positive amount for Refund", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("select[aria-label='Suggested outcome']").setValue("Refund");
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		await tickItem(wrapper, "Include ITEM-1");
		await flushPromises();
		expect(recordButton(wrapper).attributes("disabled")).toBeDefined();
	});

	it("hides the replacement columns for a Refund", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("select[aria-label='Suggested outcome']").setValue("Refund");
		await flushPromises();
		expect(wrapper.text()).not.toContain("Replacement");
		expect(wrapper.text()).not.toContain("Part qty");
		expect(wrapper.findAll(".replacement-pick")).toHaveLength(0);
	});

	it("never shows the replacement columns for a Service Call, only for Exchange/Replace", async () => {
		// Policy change 2026-09-22: a Spare Part visit's Delivery Note/Stream
		// order always carry the fixed "Spare Part" placeholder item regardless
		// of what's picked here -- Replacement (renamed from "Replacement /
		// spare part") is Exchange/Replace only now, matching the server
		// (CustomerClaimDecision._validate_items' needs_replacement) and the
		// Desk dialog (dialogs.js's updateItemColumnsVisibility).
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("select[aria-label='Suggested outcome']").setValue("Service Call");
		await flushPromises();
		await wrapper.find("select[aria-label='Service type']").setValue("Maintenance Visit");
		await flushPromises();
		expect(wrapper.findAll(".replacement-pick")).toHaveLength(0);

		await wrapper.find("select[aria-label='Service type']").setValue("Spare Part");
		await flushPromises();
		expect(wrapper.findAll(".replacement-pick")).toHaveLength(0);
	});

	it("submits the selected lines with replacement details and emits created", async () => {
		const onCreated = vi.fn();
		const onClose = vi.fn();
		const wrapper = mountDialog({ onCreated, "onUpdate:modelValue": onClose });
		await flushPromises();
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		await tickItem(wrapper, "Include ITEM-1");
		await flushPromises();

		// No free-text code box: the replacement comes from the item picker.
		expect(wrapper.findAll("input[placeholder='Item code']")).toHaveLength(0);
		const rows = wrapper.findAll("tbody tr");
		await rows[0]!.find(".replacement-pick").trigger("click");
		await flushPromises();
		expect(wrapper.find(".items-selector-stub").attributes("data-context")).toBe("sales-order");
		expect(wrapper.text()).toContain("Choose replacement for ITEM-1");
		await wrapper.find(".pick-SOFA-NEW").trigger("click");
		await flushPromises();

		// The picker closes and the row shows the chosen item.
		expect(wrapper.find(".items-selector-stub").exists()).toBe(false);
		expect(wrapper.findAll("tbody tr")[0]!.text()).toContain("New Sofa");

		await recordButton(wrapper).trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) =>
			c[0].endsWith("propose_decision"),
		);
		expect(call[1].payload).toMatchObject({
			claim: "CLM-0001",
			outcome: "Replace",
			reasoning: "Confirmed faulty.",
			// Replacement qty defaults to the decided qty, like for like.
			items: [{ claim_item: "CCI-1", qty: 2, replacement_item: "SOFA-NEW", replacement_qty: 2 }],
		});
		expect(onCreated).toHaveBeenCalledWith("CLM-0001");
		expect(onClose).toHaveBeenCalledWith(false);
	});

	it("refuses a template item and asks for a specific variant", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		await tickItem(wrapper, "Include ITEM-1");
		await flushPromises();
		await wrapper.findAll("tbody tr")[0]!.find(".replacement-pick").trigger("click");
		await flushPromises();
		await wrapper.find(".pick-CHAIR-TPL").trigger("click");
		await flushPromises();

		expect(wrapper.text()).toContain("Chair Template has variants. Choose the specific variant instead.");
		expect(wrapper.find(".items-selector-stub").exists()).toBe(true);
		expect(recordButton(wrapper).attributes("disabled")).toBeDefined();
	});

	it("blocks recording when a replacement quantity is cleared to zero", async () => {
		const wrapper = mountDialog();
		await flushPromises();
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		await tickItem(wrapper, "Include ITEM-1");
		await flushPromises();
		await wrapper.findAll("tbody tr")[0]!.find(".replacement-pick").trigger("click");
		await flushPromises();
		await wrapper.find(".pick-SOFA-NEW").trigger("click");
		await flushPromises();
		expect(recordButton(wrapper).attributes("disabled")).toBeUndefined();

		const qtyInputs = wrapper.findAll("tbody tr")[0]!.findAll("input:not([type='checkbox'])");
		await qtyInputs[qtyInputs.length - 1]!.setValue("0");
		await flushPromises();
		expect(recordButton(wrapper).attributes("disabled")).toBeDefined();
	});
});
