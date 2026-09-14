// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

vi.mock("../src/posapp/services/api", () => ({
	default: { call: vi.fn() },
}));

const { routerPush, routerReplace, routeQuery } = vi.hoisted(() => ({
	routerPush: vi.fn(),
	routerReplace: vi.fn(),
	routeQuery: {} as { sales_order?: string },
}));
vi.mock("vue-router", () => ({
	useRouter: () => ({ push: routerPush, replace: routerReplace }),
	useRoute: () => ({ query: routeQuery }),
}));

import ClaimsView from "../src/posapp/components/pos/claims/ClaimsView.vue";
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

const overview = {
	claims: [
		{
			name: "CLM-0001",
			customer: "Alice",
			sales_order: "SO-1",
			claim_type: "Damage",
			workflow_state: "Pending Approval",
			progress: "Open",
			preferred_outcome: "Replace",
			modified: "2026-09-01 10:00:00",
		},
		{
			name: "CLM-0002",
			customer: "Bob",
			sales_order: "SO-2",
			claim_type: "Fault",
			workflow_state: "Approved",
			progress: "In Progress",
			preferred_outcome: "Refund",
			modified: "2026-09-02 10:00:00",
		},
	],
	has_more: false,
	counts: { open: 2, pending: 1, approved: 1 },
	claim_types: [{ name: "Damage" }, { name: "Fault" }],
};

const detail = {
	claim: {
		name: "CLM-0001",
		customer: "Alice",
		sales_order: "SO-1",
		claim_type: "Damage",
		description: "Screen cracked",
		preferred_outcome: "Replace",
		assigned_to: "agent@example.com",
		owner: "till@example.com",
		workflow_state: "Pending Approval",
		progress: "Open",
		modified: "2026-09-01 10:00:00",
		items: [
			{ name: "CCI-1", item_code: "ITEM-1", item_name: "Widget", qty: 1, uom: "Nos", fault_details: "cracked" },
		],
	},
	decisions: [],
	actions: [],
	available_actions: [],
	progress_actions: [],
	previous_claims: [],
	can_add_decision: false,
	can_add_action: false,
};

const approverDecision = {
	name: "CCD-0001",
	claim: "CLM-0001",
	outcome: "Replace",
	service_call_type: "",
	reasoning: "Confirmed faulty.",
	differs_from_preference: 0,
	amount: 0,
	collection_required: 0,
	workflow_state: "Approved",
	rejection_reason: "",
	superseded_by: "",
	modified: "2026-09-01 11:00:00",
	items: [{ name: "CCDI-1", item_code: "ITEM-1", qty: 1 }],
	available_actions: [],
	can_add_action: true,
	actions: [
		{
			name: "CCA-0001",
			action_type: "Replace",
			service_call_type: "",
			description: "Ship replacement",
			amount: 0,
			currency: "GBP",
			execution_status: "Queued",
		},
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

const mountView = () =>
	mount(ClaimsView, {
		global: {
			mocks: { __: translate },
			components: {
				VCard: BoxStub,
				VCardTitle: BoxStub,
				VCardText: BoxStub,
				VCardActions: BoxStub,
				VDialog: BoxStub,
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

describe("ClaimsView", () => {
	beforeEach(() => {
		vi.clearAllMocks();
		delete routeQuery.sales_order;
		vi.stubGlobal("__", (value: string, args?: any[]) =>
			Array.isArray(args) ? value.replace(/\{(\d+)\}/g, (_m, i) => String(args[Number(i)] ?? "")) : value,
		);
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("list_claims")) return overview;
			if (method.endsWith("get_claim")) return detail;
			return null;
		});
	});

	it("lists claims and their counts on mount", async () => {
		const wrapper = mountView();
		await flushPromises();
		expect(wrapper.text()).toContain("CLM-0001");
		expect(wrapper.text()).toContain("CLM-0002");
		expect(wrapper.text()).toContain("Alice");
		const firstCall = (api.call as any).mock.calls[0];
		expect(firstCall[0]).toBe("posawesome.posawesome.api.claims.list_claims");
		expect(firstCall[1]).toMatchObject({ progress: "", open_only: 1, start: 0 });
	});

	it("loads detail when a claim row is clicked", async () => {
		const wrapper = mountView();
		await flushPromises();
		const row = wrapper.findAll("button").find((b) => b.text().includes("CLM-0001"))!;
		await row.trigger("click");
		await flushPromises();
		expect(api.call).toHaveBeenCalledWith("posawesome.posawesome.api.claims.get_claim", {
			claim: "CLM-0001",
		});
		expect(wrapper.text()).toContain("Screen cracked");
		expect(wrapper.text()).toContain("ITEM-1");
	});

	it("re-queries with the approval filter applied", async () => {
		const wrapper = mountView();
		await flushPromises();
		(api.call as any).mockClear();
		await wrapper.find("select[aria-label='Approval']").setValue("Approved");
		await flushPromises();
		const call = (api.call as any).mock.calls.find((c: any[]) => c[0].endsWith("list_claims"));
		expect(call[1]).toMatchObject({ approval: "Approved", start: 0 });
	});

	it("deep-links to the Sales Order screen from the claim detail", async () => {
		const wrapper = mountView();
		await flushPromises();
		const row = wrapper.findAll("button").find((b) => b.text().includes("CLM-0001"))!;
		await row.trigger("click");
		await flushPromises();

		const button = wrapper.findAll("button").find((b) => b.text() === "View Sales Order")!;
		await button.trigger("click");
		expect(routerPush).toHaveBeenCalledWith({ path: "/sales-orders", query: { sales_order: "SO-1" } });
	});

	it("pre-filters to a sales order from the route query", async () => {
		routeQuery.sales_order = "SO-9";
		const wrapper = mountView();
		await flushPromises();
		const firstCall = (api.call as any).mock.calls[0];
		expect(firstCall[1]).toMatchObject({ sales_order: "SO-9", progress: "" });
		expect(wrapper.text()).toContain("Showing claims for Sales Order SO-9");

		const clear = wrapper.findAll("button").find((b) => b.text() === "Show all claims")!;
		await clear.trigger("click");
		await flushPromises();
		expect(routerReplace).toHaveBeenCalledWith({ path: "/claims", query: {} });
		const lastCall = (api.call as any).mock.calls.at(-1);
		expect(lastCall[1]).toMatchObject({ sales_order: "", start: 0 });
	});

	it("shows a decision with its nested actions and progress move buttons", async () => {
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("list_claims")) return overview;
			if (method.endsWith("get_claim")) {
				return {
					...detail,
					claim: { ...detail.claim, workflow_state: "Approved", progress: "In Progress" },
					decisions: [approverDecision],
					progress_actions: ["Awaiting Customer", "Awaiting Engineer", "Ready to Close"],
					can_add_decision: true,
				};
			}
			return null;
		});
		const wrapper = mountView();
		await flushPromises();
		const row = wrapper.findAll("button").find((b) => b.text().includes("CLM-0001"))!;
		await row.trigger("click");
		await flushPromises();

		expect(wrapper.text()).toContain("Confirmed faulty.");
		expect(wrapper.text()).toContain("Ship replacement");
		expect(wrapper.findAll("button").find((b) => b.text() === "Propose decision")).toBeTruthy();
		expect(wrapper.findAll("button").find((b) => b.text() === "Awaiting Customer")).toBeTruthy();
	});

	it("moves claim progress and refreshes the detail", async () => {
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("list_claims")) return overview;
			if (method.endsWith("get_claim")) {
				return {
					...detail,
					claim: { ...detail.claim, workflow_state: "Approved", progress: "In Progress" },
					decisions: [approverDecision],
					progress_actions: ["Awaiting Customer", "Awaiting Engineer", "Ready to Close"],
				};
			}
			if (method.endsWith("set_claim_progress")) return { name: "CLM-0001", progress: "Awaiting Customer" };
			return null;
		});
		const wrapper = mountView();
		await flushPromises();
		const row = wrapper.findAll("button").find((b) => b.text().includes("CLM-0001"))!;
		await row.trigger("click");
		await flushPromises();

		const step = wrapper.findAll("button").find((b) => b.text() === "Awaiting Customer")!;
		await step.trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) =>
			c[0].endsWith("set_claim_progress"),
		);
		expect(call[1]).toMatchObject({ claim: "CLM-0001", progress: "Awaiting Customer" });
	});

	it("rejects a decision with a reason", async () => {
		const pendingDecision = { ...approverDecision, available_actions: ["Approve", "Reject"] };
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("list_claims")) return overview;
			if (method.endsWith("get_claim")) {
				return {
					...detail,
					claim: { ...detail.claim, workflow_state: "Approved" },
					decisions: [pendingDecision],
				};
			}
			if (method.endsWith("decision_transition")) return { name: "CCD-0001", workflow_state: "Rejected" };
			return null;
		});
		const wrapper = mountView();
		await flushPromises();
		const row = wrapper.findAll("button").find((b) => b.text().includes("CLM-0001"))!;
		await row.trigger("click");
		await flushPromises();

		const rejectButton = wrapper.findAll("button").find((b) => b.text() === "Reject")!;
		await rejectButton.trigger("click");
		await wrapper.find("textarea[aria-label='Reason']").setValue("Not eligible.");
		const confirm = wrapper.findAll("button").find((b) => b.text() === "Confirm rejection")!;
		await confirm.trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) =>
			c[0].endsWith("decision_transition"),
		);
		expect(call[1]).toMatchObject({ name: "CCD-0001", action: "Reject", reason: "Not eligible." });
	});

	it("proposes a decision from the claim detail", async () => {
		(api.call as any).mockImplementation(async (method: string) => {
			if (method.endsWith("list_claims")) return overview;
			if (method.endsWith("get_claim")) {
				return {
					...detail,
					claim: { ...detail.claim, workflow_state: "Approved" },
					can_add_decision: true,
				};
			}
			if (method.endsWith("propose_decision")) return { name: "CCD-NEW", workflow_state: "Approved" };
			return null;
		});
		const wrapper = mountView();
		await flushPromises();
		const row = wrapper.findAll("button").find((b) => b.text().includes("CLM-0001"))!;
		await row.trigger("click");
		await flushPromises();

		const propose = wrapper.findAll("button").find((b) => b.text() === "Propose decision")!;
		await propose.trigger("click");
		await flushPromises();

		// Service Call needs no replacement item or amount, so this stays focused on the
		// propose/submit wiring rather than every outcome-specific validation rule.
		await wrapper.find("select[aria-label='Approved outcome']").setValue("Service Call");
		await wrapper.find("select[aria-label='Service type']").setValue("Maintenance Visit");
		await wrapper.find("textarea[aria-label='Reasoning']").setValue("Confirmed faulty.");
		// checkbox 0 is "Collection required"; the item row checkbox comes after it.
		const itemCheckbox = wrapper
			.findAll("input[type='checkbox']")
			.find((c) => c.attributes("aria-label") === "Include ITEM-1")!;
		await itemCheckbox.setValue(true);
		await flushPromises();

		const record = wrapper.findAll("button").find((b) => b.text() === "Record decision")!;
		await record.trigger("click");
		await flushPromises();

		const call = (api.call as any).mock.calls.find((c: any[]) => c[0].endsWith("propose_decision"));
		expect(call).toBeTruthy();
		expect(call[1].payload).toMatchObject({
			claim: "CLM-0001",
			outcome: "Service Call",
			service_call_type: "Maintenance Visit",
			reasoning: "Confirmed faulty.",
		});
	});
});
