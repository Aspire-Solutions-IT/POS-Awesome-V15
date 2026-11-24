// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
	hasLegacyChargeRows,
	isOrderTypeUnverified,
	markUnverifiedCachedCharges,
} from "../src/posapp/composables/pos/invoice/shipComplete";

describe("charge rows without an order type name", () => {
	it("are legacy even when they already have ship_complete, and get marked unverified", () => {
		const rows = [{ name: "A", ship_complete: 0 }];
		expect(hasLegacyChargeRows(rows)).toBe(true);
		const [marked] = markUnverifiedCachedCharges(rows);
		expect(marked.order_type_unverified).toBe(true);
		expect(marked.ship_complete_unverified).toBeUndefined();
		expect(isOrderTypeUnverified(marked)).toBe(true);
	});

	it("are fine when the order type name is present, even empty, and a missing row is not unverified", () => {
		const rows = [{ name: "A", ship_complete: 0, order_type_name: "" }, { name: "B", ship_complete: 1, order_type_name: "DHD" }];
		expect(hasLegacyChargeRows(rows)).toBe(false);
		expect(markUnverifiedCachedCharges(rows).some(isOrderTypeUnverified)).toBe(false);
		expect(isOrderTypeUnverified(null)).toBe(false);
	});
});

describe("fetch_delivery_charges with a cached row lacking order_type_name", () => {
	beforeEach(() => {
		vi.resetModules();
		setActivePinia(createPinia());
		(window as any).__ = (value: string) => value;
		(window as any).frappe = {
			call: vi.fn(),
			datetime: { nowdate: () => "2026-04-09", get_today: () => "2026-04-09" },
		};
	});

	const load = async () => {
		const offlineCache = await import("../src/offline/cache");
		const { useUIStore } = await import("../src/posapp/stores/uiStore");
		useUIStore().setPosProfile({ name: "POS-1", company: "Test Company", currency: "GBP" } as any);
		offlineCache.saveDeliveryChargesCache("POS-1", "CUST-1", [
			{ name: "DEL-1", rate: 5, ship_complete: 0 },
		]);
		const { useInvoiceItems } = await import("../src/posapp/composables/pos/invoice/useInvoiceItems");
		return useInvoiceItems(ref("Order"));
	};

	it("refreshes once online and uses the server row when it names the order type", async () => {
		const items = await load();
		(window as any).frappe.call = vi
			.fn()
			.mockRejectedValueOnce(new Error("blip"))
			.mockResolvedValueOnce({
				message: [{ name: "DEL-1", rate: 5, ship_complete: 0, order_type_name: "DHD" }],
			});
		await items.fetch_delivery_charges("CUST-1");
		expect((window as any).frappe.call).toHaveBeenCalledTimes(2);
		expect(items.delivery_charges.value[0].order_type_name).toBe("DHD");
		expect(isOrderTypeUnverified(items.delivery_charges.value[0])).toBe(false);
	});

	it("marks the row unverified when it still cannot be verified", async () => {
		const items = await load();
		(window as any).frappe.call = vi.fn().mockRejectedValue(new Error("offline"));
		await items.fetch_delivery_charges("CUST-1");
		expect(isOrderTypeUnverified(items.delivery_charges.value[0])).toBe(true);
	});
});

describe("get_addresses supersession", () => {
	const setup = async () => {
		vi.resetModules();
		setActivePinia(createPinia());
		(window as any).__ = (value: string) => value;
		const pending: Array<{ args: any; callback: (r: any) => void }> = [];
		(window as any).frappe = {
			call: vi.fn((opts: any) => pending.push({ args: opts.args, callback: opts.callback })),
			datetime: { nowdate: () => "2026-04-09", get_today: () => "2026-04-09" },
		};
		const { useInvoiceDetails } = await import("../src/posapp/composables/pos/invoice/useInvoiceDetails");
		const invoiceDoc = ref<any>({ customer: "CUST-1", shipping_address_name: null });
		const details = useInvoiceDetails({
			invoiceDoc,
			posProfile: ref({}),
			invoiceType: ref("Order"),
		} as any);
		return { details, invoiceDoc, pending };
	};

	it("a late plain list response cannot clear the shipping address chosen after a save", async () => {
		const { details, invoiceDoc, pending } = await setup();
		details.get_addresses(); // list request that will answer late, without the new address
		const saved = details.get_addresses({ select: "NEW-ADDR" });
		pending[1].callback({ message: [{ name: "NEW-ADDR", address_line1: "1 High St" }] });
		expect(await saved).toBe(true);
		expect(invoiceDoc.value.shipping_address_name).toBe("NEW-ADDR");
		expect(invoiceDoc.value.customer_address).toBe("NEW-ADDR");

		pending[0].callback({ message: [{ name: "OTHER", address_line1: "x" }] });
		expect(invoiceDoc.value.shipping_address_name).toBe("NEW-ADDR");
		expect(details.addresses.value.map((a: any) => a.name)).toEqual(["NEW-ADDR"]);
	});

	it("a list response for a customer that was since replaced is ignored", async () => {
		const { details, invoiceDoc, pending } = await setup();
		const saved = details.get_addresses({ select: "NEW-ADDR" });
		invoiceDoc.value.customer = "CUST-2";
		pending[0].callback({ message: [{ name: "NEW-ADDR" }] });
		expect(await saved).toBe(false);
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
		expect(details.addresses.value).toEqual([]);
	});

	it("invalidateAddressRequests drops responses already in flight", async () => {
		const { details, invoiceDoc, pending } = await setup();
		invoiceDoc.value.shipping_address_name = "KEEP";
		details.get_addresses();
		details.invalidateAddressRequests();
		pending[0].callback({ message: [] });
		expect(invoiceDoc.value.shipping_address_name).toBe("KEEP");
	});

	it("a selection the caller no longer wants is not applied", async () => {
		const { details, invoiceDoc, pending } = await setup();
		let wanted = true;
		const saved = details.get_addresses({ select: "NEW-ADDR", isStillWanted: () => wanted });
		wanted = false;
		pending[0].callback({ message: [{ name: "NEW-ADDR" }] });
		expect(await saved).toBe(false);
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
	});
});
