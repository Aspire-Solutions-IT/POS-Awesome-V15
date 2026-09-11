// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

vi.mock("../src/posapp/services/api", () => ({
	default: { call: vi.fn() },
}));

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
		const select = wrapper.find("select[aria-label='Approved outcome']")
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
		await wrapper.find("select[aria-label='Approved outcome']").setValue("Refund");
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		await tickItem(wrapper, "Include ITEM-1");
		await flushPromises();
		expect(recordButton(wrapper).attributes("disabled")).toBeDefined();
	});

	it("submits the selected lines with replacement details and emits created", async () => {
		const onCreated = vi.fn();
		const onClose = vi.fn();
		const wrapper = mountDialog({ onCreated, "onUpdate:modelValue": onClose });
		await flushPromises();
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		await tickItem(wrapper, "Include ITEM-1");
		await flushPromises();

		const rows = wrapper.findAll("tbody tr");
		await rows[0]!.find("input[placeholder='Item code']").setValue("ITEM-1-NEW");
		await flushPromises();

		await recordButton(wrapper).trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) =>
			c[0].endsWith("propose_decision"),
		);
		expect(call[1].payload).toMatchObject({
			claim: "CLM-0001",
			outcome: "Replace",
			reasoning: "Confirmed faulty.",
			items: [{ claim_item: "CCI-1", qty: 2, replacement_item: "ITEM-1-NEW" }],
		});
		expect(onCreated).toHaveBeenCalledWith("CLM-0001");
		expect(onClose).toHaveBeenCalledWith(false);
	});
});
