// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";

vi.mock("../src/posapp/services/api", () => ({
	default: { call: vi.fn() },
}));

const { routerReplace } = vi.hoisted(() => ({ routerReplace: vi.fn() }));
vi.mock("vue-router", () => ({
	useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
}));

import CommissionView from "../src/posapp/components/pos/commission/CommissionView.vue";
import api from "../src/posapp/services/api";

const flushPromises = async () => {
	for (let i = 0; i < 5; i++) await Promise.resolve();
	await new Promise((resolve) => setTimeout(resolve, 0));
};

const response = {
	rows: [
		{
			name: "SO-1",
			transaction_date: "2026-11-01",
			customer: "C1",
			customer_name: "Alice Ltd",
			status: "To Deliver",
			delivered: 0,
			net_value: 500,
			commission_rate: 10,
			commission: 50,
		},
		{
			name: "SO-2",
			transaction_date: "2026-11-02",
			customer: "C2",
			customer_name: "Bob Ltd",
			status: "Completed",
			delivered: 1,
			net_value: 1000,
			commission_rate: 10,
			commission: 100,
		},
	],
	totals: { orders: 2, net_value: 1500, commission: 150 },
	currency: "GBP",
	limit: 50,
	offset: 0,
};

const Box = defineComponent({
	setup: (_, { slots }) => () => h("div", {}, slots.default?.()),
});
const Table = defineComponent({
	setup: (_, { slots }) => () => h("table", {}, slots.default?.()),
});
const Btn = defineComponent({
	emits: ["click"],
	setup: (_, { slots, emit }) => () => h("button", { onClick: () => emit("click") }, slots.default?.()),
});
const Field = defineComponent({
	props: { modelValue: { type: [String, Boolean], default: "" }, label: { type: String, default: "" } },
	setup: (props) => () => h("input", { "aria-label": props.label }),
});

const mountView = () => {
	const translate = (text: string, args?: any[]) =>
		Array.isArray(args) ? text.replace(/\{(\d+)\}/g, (_m, i) => String(args[Number(i)] ?? "")) : text;
	(globalThis as any).__ = translate;
	return mount(CommissionView, {
		global: {
			mocks: { __: translate },
			components: {
				VCard: Box,
				VAlert: Box,
				VChip: Box,
				VTable: Table,
				VBtn: Btn,
				VCheckbox: Field,
				VTextField: Field,
			},
		},
	});
};

describe("CommissionView", () => {
	beforeEach(() => {
		routerReplace.mockReset();
		vi.mocked(api.call).mockReset();
		vi.mocked(api.call).mockResolvedValue(response as any);
		(globalThis as any).__ = (text: string, args?: any[]) =>
			Array.isArray(args) ? text.replace(/\{(\d+)\}/g, (_m, i) => String(args[Number(i)] ?? "")) : text;
		(globalThis as any).frappe = {
			boot: { posa_partner_mode: { partners: ["P"], allowed_methods: [] } },
			format: (value: any) => `£${value}`,
			datetime: { str_to_user: (v: string) => v },
		};
	});

	it("renders the partner's orders and totals", async () => {
		const wrapper = mountView();
		await flushPromises();

		expect(routerReplace).not.toHaveBeenCalled();
		expect(api.call).toHaveBeenCalledWith(
			"posawesome.posawesome.api.partner_commission.get_partner_commission",
			expect.objectContaining({ delivered_only: 0 }),
		);
		const text = wrapper.text();
		expect(text).toContain("My Commission");
		expect(text).toContain("Alice Ltd");
		expect(text).toContain("SO-2");
		expect(text).toContain("£150");
	});

	it("sends anyone who is not a partner back to the POS", async () => {
		(globalThis as any).frappe.boot = {};
		mountView();
		await flushPromises();

		expect(routerReplace).toHaveBeenCalledWith("/pos");
		expect(api.call).not.toHaveBeenCalled();
	});
});
