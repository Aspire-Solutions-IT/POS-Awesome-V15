import { describe, expect, it, vi } from "vitest";

import { _applyItemDetailPayload } from "../src/posapp/components/pos/invoice_utils/item_updates";

const makeContext = () => ({
	pos_profile: {
		warehouse: "Main WH",
		default_ns_warehouse: "NS Default WH",
		posa_auto_set_batch: false,
	},
	price_list_currency: "GBP",
	selected_currency: "GBP",
	currency_precision: 2,
	flt: (value: any) => Number(value),
	update_qty_limits: vi.fn(),
	_getPlcConversionRate: () => 1,
	_applyPriceListRate: vi.fn(),
});

const makePayload = (warehouse: string) => ({
	stock_uom: "Nos",
	uom: "Nos",
	conversion_factor: 1,
	item_uoms: [{ uom: "Nos", conversion_factor: 1 }],
	allow_change_warehouse: 1,
	locked_price: 0,
	description: "",
	item_tax_template: "",
	discount_percentage: 0,
	// ERPNext resolves this from the doc / item default when the args carry no
	// warehouse, so it is frequently NOT the warehouse the operator picked.
	warehouse,
	has_batch_no: 0,
	has_serial_no: 0,
	serial_no: null,
	batch_no: null,
	is_stock_item: 1,
	is_fixed_asset: 0,
	allow_alternative_item: 0,
	actual_qty: 4,
	price_list_rate: 100,
	currency: "GBP",
	serial_no_data: [],
});

describe("_applyItemDetailPayload NS warehouse preservation", () => {
	it("keeps the chosen warehouse on an NS item when the manual flag is present", () => {
		const item: any = {
			item_code: "NS-1001",
			warehouse: "Peterborough WH",
			_warehouse_selected_manually: true,
			qty: 1,
			item_uoms: [],
		};

		_applyItemDetailPayload(makeContext(), item, makePayload("NS Default WH"));

		expect(item.warehouse).toBe("Peterborough WH");
	});

	it("keeps the chosen warehouse on an NS item after a reload drops the manual flag", () => {
		// `load_invoice` replaces cart rows with the server's, which carry no
		// underscore-prefixed flags — the warehouse on the row must still win.
		const item: any = {
			item_code: "NS-1001",
			warehouse: "Peterborough WH",
			qty: 1,
			item_uoms: [],
		};

		_applyItemDetailPayload(makeContext(), item, makePayload("NS Default WH"));

		expect(item.warehouse).toBe("Peterborough WH");
	});

	it("fills the NS default when the row has no warehouse at all", () => {
		const item: any = { item_code: "NS-1001", qty: 1, item_uoms: [] };

		_applyItemDetailPayload(makeContext(), item, makePayload("NS Default WH"));

		expect(item.warehouse).toBe("NS Default WH");
	});

	it("still lets the server payload set the warehouse for non-NS items", () => {
		const item: any = {
			item_code: "WIDGET-1",
			warehouse: "Main WH",
			qty: 1,
			item_uoms: [],
		};

		_applyItemDetailPayload(makeContext(), item, makePayload("Other WH"));

		expect(item.warehouse).toBe("Other WH");
	});
});
