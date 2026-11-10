// @vitest-environment jsdom

import { describe, expect, it } from "vitest";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";
import CartItemRow from "../src/posapp/components/pos/invoice/CartItemRow.vue";

const ButtonStub = defineComponent({
	props: { disabled: Boolean },
	setup(props, { slots }) {
		return () =>
			h("button", { disabled: props.disabled }, slots.default?.());
	},
});

function mountRow(isCover = true) {
	return mount(CartItemRow, {
		props: {
			item: {
				item_code: "SG-1",
				item_name: "Cover",
				is_staingard_item: isCover ? 1 : 0,
				qty: 1,
				rate: 40,
				item_uoms: [{ uom: "Nos" }, { uom: "Box" }],
				uom: "Nos",
			},
			visibleColumns: [
				"item_name",
				"qty",
				"uom",
				"rate",
				"discount_percentage",
				"discount_amount",
				"posa_is_offer",
				"actions",
				"data-table-expand",
			].map((key) => ({ key })),
			posProfile: {
				posa_allow_line_item_name_override: 1,
				posa_allow_user_to_edit_rate: 1,
				posa_allow_user_to_edit_item_discount: 1,
			},
			formatFloat: String,
			formatCurrency: String,
			currencySymbol: () => "£",
			isNegative: () => false,
		},
		global: {
			components: { VBtn: ButtonStub },
			stubs: {
				VIcon: true,
				VChip: true,
				VTooltip: true,
				VTextField: true,
				VSelect: true,
			},
		},
	});
}

describe("Stainguard cart row", () => {
	it("disables quantity, UOM, offer, delete and detail controls", () => {
		const row = mountRow();
		expect(row.findAll("button").length, row.html()).toBeGreaterThan(4);
		expect(
			row.findAll("button").every((button) => button.element.disabled),
		).toBe(true);
		expect(row.find('[aria-label="Edit item name"]').exists()).toBe(false);
	});

	it("does not open inline quantity, price or discount editors", async () => {
		const row = mountRow();
		for (const cell of row.findAll(".amount-value"))
			await cell.trigger("click");
		expect(row.findAll("v-text-field-stub")).toHaveLength(0);
		expect(row.findAll("v-select-stub")).toHaveLength(0);
	});

	it("leaves ordinary items editable", () => {
		const row = mountRow(false);
		expect(row.find('[aria-label="Edit item name"]').exists()).toBe(true);
		expect(
			row.findAll("button").every((button) => !button.element.disabled),
		).toBe(true);
	});
});
