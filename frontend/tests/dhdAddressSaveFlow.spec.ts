// @vitest-environment jsdom

import { createPinia, setActivePinia } from "pinia";
import { ref } from "vue";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Drives the real address loader with deferred server responses, as Payments.vue wires it.
const setup = async () => {
	vi.resetModules();
	setActivePinia(createPinia());
	(window as any).__ = (value: string) => value;
	const pending: Array<{ args: any; callback: (r: any) => void; error: () => void }> = [];
	(window as any).frappe = {
		call: vi.fn((opts: any) => pending.push({ args: opts.args, callback: opts.callback, error: opts.error })),
		datetime: { nowdate: () => "2026-04-09", get_today: () => "2026-04-09" },
	};
	const { useInvoiceDetails } = await import("../src/posapp/composables/pos/invoice/useInvoiceDetails");
	const { useDhdAddressSave } = await import("../src/posapp/composables/pos/payments/useDhdAddressSave");
	const invoiceDoc = ref<any>({
		customer: "CUST-1",
		shipping_address_name: "OLD-ADDR",
		customer_address: "OLD-ADDR",
	});
	const details = useInvoiceDetails({ invoiceDoc, posProfile: ref({}), invoiceType: ref("Order") } as any);
	const notify = vi.fn();
	const charge = ref("Home Delivery");
	const dhdSelected = ref(true);
	const flow = useDhdAddressSave({
		getDoc: () => invoiceDoc.value,
		getCharge: () => charge.value,
		isDhdChargeSelected: () => dhdSelected.value,
		getAddresses: details.get_addresses,
		invalidateAddressRequests: details.invalidateAddressRequests,
		addresses: details.addresses,
		normalizeAddress: (a: any) => ({ ...a, display_title: a.name }),
		clearStoreCollectionSelection: () => {},
		notify,
	});
	let nextId = 0;
	// What the form does: announce the save, then (POST done) hand over the saved row.
	const startSave = (name: string, customer = "CUST-1") => {
		const saveId = ++nextId;
		flow.onSaving({ saveId });
		const settle = vi.fn();
		const saved = () =>
			flow.onSaved({ saveId, name, customer, deliveryCharge: "Home Delivery", settle });
		return { saveId, settle, saved };
	};
	return { flow, details, invoiceDoc, pending, notify, charge, dhdSelected, startSave };
};

const row = (name: string) => ({ name, address_line1: "1 High St" });
const flush = async () => {
	for (let i = 0; i < 5; i += 1) await Promise.resolve();
};

describe("DHD address save flow", () => {
	beforeEach(() => vi.clearAllMocks());

	it("clears the old selection and blocks progression until the new one is confirmed", async () => {
		const { flow, invoiceDoc, pending, notify, startSave } = await setup();
		expect(flow.blockWhilePending()).toBe(false);

		const save = startSave("NEW-ADDR");
		// POST in flight: the old address must not stand in, and progression is blocked.
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
		expect(invoiceDoc.value.customer_address).toBeNull();
		expect(flow.pending.value).toBe(true);
		expect(flow.blockWhilePending()).toBe(true);
		expect(notify).toHaveBeenCalledWith(expect.stringContaining("still being saved"), "warning");

		const done = save.saved();
		await flush();
		// POST done, picker reload still outstanding: still pending, still blocked, nothing settled.
		expect(flow.blockWhilePending()).toBe(true);
		expect(save.settle).not.toHaveBeenCalled();

		pending[0].callback({ message: [row("OLD-ADDR"), row("NEW-ADDR")] });
		await done;
		expect(invoiceDoc.value.shipping_address_name).toBe("NEW-ADDR");
		expect(invoiceDoc.value.customer_address).toBe("NEW-ADDR");
		expect(save.settle).toHaveBeenCalledWith({ status: "confirmed" });
		expect(flow.pending.value).toBe(false);
		expect(flow.blockWhilePending()).toBe(false);
	});

	it("selects the saved address by name when the reload fails, showing only the server's data", async () => {
		const { flow, details, invoiceDoc, pending, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		const done = save.saved();
		pending[0].error();
		await done;
		expect(invoiceDoc.value.shipping_address_name).toBe("NEW-ADDR");
		expect(invoiceDoc.value.customer_address).toBe("NEW-ADDR");
		// No typed text: just the persisted name.
		expect(details.addresses.value).toEqual([{ name: "NEW-ADDR", display_title: "NEW-ADDR" }]);
		expect(save.settle).toHaveBeenCalledWith({ status: "confirmed" });
		expect(flow.pending.value).toBe(false);
	});

	it("falls back to the name when the reloaded list lacks the row", async () => {
		const { invoiceDoc, pending, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		const done = save.saved();
		pending[0].callback({ message: [row("OTHER")] });
		await done;
		expect(invoiceDoc.value.shipping_address_name).toBe("NEW-ADDR");
		expect(save.settle).toHaveBeenCalledWith({ status: "confirmed" });
	});

	it("reports a retryable failure and never restores the old selection when nothing can be selected", async () => {
		const { flow, invoiceDoc, pending, notify, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		// Applying the selection fails as well.
		Object.defineProperty(invoiceDoc.value, "shipping_address_name", {
			get: () => null,
			set: () => {},
			configurable: true,
		});
		const done = save.saved();
		pending[0].error();
		await done;
		expect(save.settle).toHaveBeenCalledWith({ status: "failed" });
		expect(notify).toHaveBeenCalledWith(expect.stringContaining("Press Retry"), "error");
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
		expect(invoiceDoc.value.customer_address).not.toBe("OLD-ADDR");
		expect(flow.pending.value).toBe(false);
	});

	it("restores the earlier pick only when the POST itself failed", async () => {
		const { flow, invoiceDoc, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		flow.onSaveEnded({ saveId: save.saveId, reason: "failed" });
		expect(invoiceDoc.value.shipping_address_name).toBe("OLD-ADDR");
		expect(flow.pending.value).toBe(false);

		const second = startSave("NEW-ADDR");
		flow.onSaveEnded({ saveId: second.saveId, reason: "cancelled" });
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
	});

	it("saving A then editing and saving B: A's late reload cannot select A", async () => {
		const { flow, invoiceDoc, pending, startSave } = await setup();
		const a = startSave("ADDR-A");
		const doneA = a.saved();
		// The cashier edits the form: the form cancels A, then saves B.
		flow.onSaveEnded({ saveId: a.saveId, reason: "cancelled" });
		const b = startSave("ADDR-B");
		const doneB = b.saved();

		pending[0].callback({ message: [row("ADDR-A")] });
		await doneA;
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
		expect(a.settle).not.toHaveBeenCalledWith({ status: "confirmed" });
		expect(flow.pending.value).toBe(true);

		pending[1].callback({ message: [row("ADDR-A"), row("ADDR-B")] });
		await doneB;
		expect(invoiceDoc.value.shipping_address_name).toBe("ADDR-B");
		expect(b.settle).toHaveBeenCalledWith({ status: "confirmed" });
	});

	it("an explicit pick of another address mid-save wins and the save does not override it", async () => {
		const { flow, invoiceDoc, pending, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		const done = save.saved();
		await flush();
		// handleShippingAddressSelection: abandon the save, then apply the pick.
		flow.abandon();
		invoiceDoc.value.shipping_address_name = "PICKED";
		invoiceDoc.value.customer_address = "PICKED";
		expect(flow.pending.value).toBe(false);
		expect(flow.blockWhilePending()).toBe(false);

		pending[0].callback({ message: [row("PICKED"), row("NEW-ADDR")] });
		await done;
		expect(invoiceDoc.value.shipping_address_name).toBe("PICKED");
		expect(invoiceDoc.value.customer_address).toBe("PICKED");
		expect(save.settle).toHaveBeenCalledWith({ status: "superseded" });
	});

	it("a pick during the POST wins as well: the late saved response is dropped", async () => {
		const { flow, invoiceDoc, pending, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		flow.abandon();
		invoiceDoc.value.shipping_address_name = "PICKED";
		await save.saved();
		expect(pending).toHaveLength(0);
		expect(invoiceDoc.value.shipping_address_name).toBe("PICKED");
		expect(save.settle).toHaveBeenCalledWith({ status: "superseded" });
	});

	it("a superseded reload never enters the typed-values fallback", async () => {
		const { flow, details, invoiceDoc, pending, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		const done = save.saved();
		await flush();
		// The customer changes while the reload is outstanding.
		invoiceDoc.value.customer = "CUST-2";
		flow.abandon();
		pending[0].callback({ message: [] });
		await done;
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
		expect(details.addresses.value).toEqual([]);
		expect(save.settle).toHaveBeenCalledWith({ status: "superseded" });
		expect(save.settle).toHaveBeenCalledTimes(1);
	});

	it("repeats a reload that a plain list request overtook, instead of falling back", async () => {
		const { details, invoiceDoc, pending, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		const done = save.saved();
		await flush();
		details.get_addresses(); // e.g. the payment dialog reloading the list
		pending[0].callback({ message: [row("NEW-ADDR")] }); // overtaken: ignored
		await flush();
		expect(pending).toHaveLength(3);
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
		pending[2].callback({ message: [row("NEW-ADDR")] });
		await done;
		expect(invoiceDoc.value.shipping_address_name).toBe("NEW-ADDR");
		expect(save.settle).toHaveBeenCalledWith({ status: "confirmed" });
	});

	it("a charge that stops being DHD drops the save and settles it as superseded", async () => {
		const { flow, dhdSelected, invoiceDoc, pending, startSave } = await setup();
		const save = startSave("NEW-ADDR");
		const done = save.saved();
		await flush();
		dhdSelected.value = false;
		pending[0].callback({ message: [row("NEW-ADDR")] });
		await done;
		expect(invoiceDoc.value.shipping_address_name).toBeNull();
		expect(save.settle).toHaveBeenCalledWith({ status: "superseded" });
		expect(flow.pending.value).toBe(false);
	});
});
