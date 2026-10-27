// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

import PaymentSplitGroups from "../src/posapp/components/pos/payments/PaymentSplitGroups.vue";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});

const ButtonStub = defineComponent({
	props: { loading: Boolean, disabled: Boolean },
	emits: ["click"],
	setup(props, { attrs, slots, emit }) {
		return () =>
			h(
				"button",
				{
					"data-test": attrs["data-test"],
					"data-loading": String(props.loading),
					onClick: () => emit("click"),
				},
				slots.default?.(),
			);
	},
});

const groups = [
	{ group_id: "default", label: "In Stock", row_ids: ["r1"] },
	{ group_id: "supply-back-order", label: "Back Order", row_ids: ["r2"] },
];
const items = [
	{ posa_row_id: "r1", item_code: "TABLE", qty: 1, rate: 100 },
	{ posa_row_id: "r2", item_code: "SOFA", qty: 1, rate: 900 },
];

function mountGroups(props: Record<string, any> = {}) {
	return mount(PaymentSplitGroups, {
		props: { groups, items, defaultGroupId: "default", formatCurrency: (v: number) => String(v), ...props },
		global: {
			components: { VRow: BoxStub, VCol: BoxStub, VBtn: ButtonStub, VSelect: BoxStub },
			provide: { frappe: { _: (value: string) => value } },
		},
	});
}

describe("PaymentSplitGroups estimate delivery", () => {
	beforeEach(() => {
		vi.stubGlobal("frappe", { _: (value: string) => value });
	});

	it("always offers the estimate button and emits estimate-windows", async () => {
		const onEstimateWindows = vi.fn();
		const wrapper = mountGroups({ windowsLoading: true, onEstimateWindows });

		const button = wrapper.find('[data-test="estimate-group-windows"]');
		expect(button.exists()).toBe(true);
		expect(button.attributes("data-loading")).toBe("true");
		expect(wrapper.find('[data-test="split-group-window"]').exists()).toBe(false);

		await button.trigger("click");
		expect(onEstimateWindows).toHaveBeenCalledTimes(1);
	});

	it("shows each group's window beside its title", () => {
		const wrapper = mountGroups({
			groupWindows: { default: "12-10-2026 - 16-10-2026", "supply-back-order": "18-01-2027 - 22-01-2027" },
		});

		const windows = wrapper.findAll('[data-test="split-group-window"]').map((node) => node.text());
		expect(windows).toEqual(["12-10-2026 - 16-10-2026", "18-01-2027 - 22-01-2027"]);
	});
});
