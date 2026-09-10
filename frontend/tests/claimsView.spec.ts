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
		items: [
			{ name: "CCI-1", item_code: "ITEM-1", item_name: "Widget", qty: 1, uom: "Nos", fault_details: "cracked" },
		],
	},
	actions: [],
	available_actions: [],
	previous_claims: [],
	can_add_action: false,
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

const mountView = () =>
	mount(ClaimsView, {
		global: {
			mocks: { __: translate },
			components: {
				VCard: BoxStub,
				VAlert: BoxStub,
				VTable: BoxStub,
				VBtn: VBtnStub,
				VTextField: VTextFieldStub,
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
		expect(firstCall[1]).toMatchObject({ progress: "Open", start: 0 });
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
});
