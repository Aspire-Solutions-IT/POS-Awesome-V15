import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	getPartnerMode,
	installPartnerCallGuard,
	isMethodAllowedForPartner,
	isPartnerMode,
	isRouteAllowedForPartner,
	resolvePartnerCallArgs,
	setPartnerCustomerProvider,
} from "../src/posapp/utils/partnerMode";

const API = "posawesome.posawesome.api.";

const bootConfig = () => ({
	partners: ["SP-A"],
	allowed_methods: [`${API}items.get_items`, `${API}sales_orders.update_sales_order`, `${API}utils.get_active_pos_profile`],
	customer_methods: [`${API}items.get_items`],
	shorthand_allowed: ["logout", "ping"],
	framework_denied: ["frappe.client.insert", "frappe.client.set_value", "frappe.desk.form.save."],
	framework_allowed: ["frappe.core.doctype.user.user.switch_theme"],
});

const setBoot = (config: unknown) => {
	(globalThis as any).frappe = { boot: config ? { posa_partner_mode: config } : {} };
};

describe("partner mode flag", () => {
	afterEach(() => {
		delete (globalThis as any).frappe;
	});

	it("is off without a boot payload", () => {
		setBoot(null);
		expect(isPartnerMode()).toBe(false);
		expect(getPartnerMode()).toBeNull();
	});

	it("is on with the boot payload", () => {
		setBoot(bootConfig());
		expect(isPartnerMode()).toBe(true);
		expect(getPartnerMode()?.partners).toEqual(["SP-A"]);
	});

	it("is off when frappe itself is missing", () => {
		delete (globalThis as any).frappe;
		expect(isPartnerMode()).toBe(false);
	});

	it("tolerates a partial payload", () => {
		setBoot({ partners: [] });
		expect(getPartnerMode()?.allowed_methods).toEqual([]);
	});
});

describe("isMethodAllowedForPartner (mirrors the server gate)", () => {
	const config = bootConfig();

	it("allows everything when not in partner mode", () => {
		expect(isMethodAllowedForPartner(`${API}payments.create_payment_request`, null)).toBe(true);
	});

	it("allows only the listed app methods", () => {
		expect(isMethodAllowedForPartner(`${API}items.get_items`, config)).toBe(true);
		for (const method of [
			`${API}payments.create_payment_request`,
			`${API}employees.get_terminal_employees`,
			`${API}utilities.get_server_usage`,
			"customer_due_dates.process_notes.api.get_process_notes",
			"erpnext.accounts.party.get_party_details",
		]) {
			expect(isMethodAllowedForPartner(method, config), method).toBe(false);
		}
	});

	it("allows framework reads but not the denied writes", () => {
		expect(isMethodAllowedForPartner("frappe.client.get_list", config)).toBe(true);
		expect(isMethodAllowedForPartner("frappe.desk.search.search_link", config)).toBe(true);
		expect(isMethodAllowedForPartner("frappe.client.insert", config)).toBe(false);
		expect(isMethodAllowedForPartner("frappe.client.set_value", config)).toBe(false);
		expect(isMethodAllowedForPartner("frappe.desk.form.save.savedocs", config)).toBe(false);
	});

	it("honours the framework exceptions", () => {
		expect(isMethodAllowedForPartner("frappe.core.doctype.user.user.switch_theme", config)).toBe(true);
	});

	it("allows the shorthand handlers", () => {
		expect(isMethodAllowedForPartner("logout", config)).toBe(true);
		expect(isMethodAllowedForPartner("upload_file", config)).toBe(false);
	});

	it("reads only the part before the first slash, as Frappe does", () => {
		expect(isMethodAllowedForPartner(`${API}payments.create_payment_request/frappe.client.get_list`, config)).toBe(false);
		expect(isMethodAllowedForPartner("frappe.client.get_list/anything", config)).toBe(true);
	});

	it("refuses an empty method", () => {
		expect(isMethodAllowedForPartner("", config)).toBe(false);
		expect(isMethodAllowedForPartner("   ", config)).toBe(false);
	});
});

describe("isRouteAllowedForPartner", () => {
	it("allows the POS and the order list only", () => {
		expect(isRouteAllowedForPartner("/pos")).toBe(true);
		expect(isRouteAllowedForPartner("/sales-orders")).toBe(true);
		expect(isRouteAllowedForPartner("/sales-orders?name=SO-1")).toBe(true);
		for (const path of ["/payments", "/claims", "/closing", "/cash-movement", "/dashboard", "/reports", "/orders", "/gift-cards", "/barcode", "/customer-display", "/posx"]) {
			expect(isRouteAllowedForPartner(path), path).toBe(false);
		}
	});
});

describe("installPartnerCallGuard", () => {
	let realCall: ReturnType<typeof vi.fn>;
	let realXcall: ReturnType<typeof vi.fn>;
	let frappeStub: any;

	beforeEach(() => {
		realCall = vi.fn(() => Promise.resolve({ message: "real" }));
		realXcall = vi.fn(() => Promise.resolve("real"));
		frappeStub = { boot: { posa_partner_mode: bootConfig() }, call: realCall, xcall: realXcall };
		(globalThis as any).frappe = frappeStub;
	});

	afterEach(() => {
		delete (globalThis as any).frappe;
	});

	it("passes allowed calls through untouched", async () => {
		installPartnerCallGuard(frappeStub);
		const callback = vi.fn();
		await frappeStub.call({ method: `${API}utils.get_active_pos_profile`, args: { a: 1 }, callback });
		expect(realCall).toHaveBeenCalledWith({ method: `${API}utils.get_active_pos_profile`, args: { a: 1 }, callback });
		await frappeStub.call("frappe.client.get_list", { doctype: "Customer" });
		expect(realCall).toHaveBeenLastCalledWith("frappe.client.get_list", { doctype: "Customer" });
		await frappeStub.xcall(`${API}utils.get_active_pos_profile`, { b: 2 });
		expect(realXcall).toHaveBeenCalledWith(`${API}utils.get_active_pos_profile`, { b: 2 });
	});

	it("answers disallowed calls quietly without touching the network", async () => {
		installPartnerCallGuard(frappeStub);
		const callback = vi.fn();
		const error = vi.fn();
		const response = await frappeStub.call({ method: `${API}payments.create_payment_request`, callback, error });
		expect(response).toEqual({ message: undefined });
		expect(await frappeStub.call(`${API}employees.get_terminal_employees`, {})).toEqual({ message: undefined });
		expect(await frappeStub.xcall(`${API}utilities.get_server_usage`)).toBeUndefined();
		expect(realCall).not.toHaveBeenCalled();
		expect(realXcall).not.toHaveBeenCalled();
		expect(callback).not.toHaveBeenCalled();
		expect(error).not.toHaveBeenCalled();
	});

	it("also silences denied framework writes", async () => {
		installPartnerCallGuard(frappeStub);
		await frappeStub.call({ method: "frappe.client.set_value", args: {} });
		expect(realCall).not.toHaveBeenCalled();
	});

	it("installs only once", async () => {
		installPartnerCallGuard(frappeStub);
		const guarded = frappeStub.call;
		installPartnerCallGuard(frappeStub);
		expect(frappeStub.call).toBe(guarded);
		await frappeStub.call({ method: `${API}utils.get_active_pos_profile` });
		expect(realCall).toHaveBeenCalledTimes(1);
	});

	it("does nothing outside partner mode", () => {
		delete frappeStub.boot.posa_partner_mode;
		installPartnerCallGuard(frappeStub);
		expect(frappeStub.call).toBe(realCall);
		expect(frappeStub.xcall).toBe(realXcall);
	});

	it("keeps properties of the original call function", () => {
		(realCall as any).extra = "kept";
		installPartnerCallGuard(frappeStub);
		expect(frappeStub.call.extra).toBe("kept");
	});
});

describe("customer supplied to partner calls", () => {
	const config = bootConfig();
	const ITEMS = `${API}items.get_items`;

	afterEach(() => {
		setPartnerCustomerProvider(() => null);
		delete (globalThis as any).frappe;
	});

	it("leaves methods that don't take a customer alone", () => {
		setPartnerCustomerProvider(() => "CUST-A");
		const args = { a: 1 };
		expect(resolvePartnerCallArgs(`${API}utils.get_active_pos_profile`, args, config)).toBe(args);
	});

	it("keeps a customer the caller already named (the server checks it)", () => {
		setPartnerCustomerProvider(() => "CUST-A");
		const args = { customer: "CUST-B" };
		expect(resolvePartnerCallArgs(ITEMS, args, config)).toBe(args);
	});

	it("fills in the selected customer when the call omits it", () => {
		setPartnerCustomerProvider(() => "CUST-A");
		expect(resolvePartnerCallArgs(ITEMS, { price_list: "X" }, config)).toEqual({
			price_list: "X",
			customer: "CUST-A",
		});
		expect(resolvePartnerCallArgs(ITEMS, { customer: "" }, config)).toEqual({ customer: "CUST-A" });
		expect(resolvePartnerCallArgs(ITEMS, undefined, config)).toEqual({ customer: "CUST-A" });
	});

	it("does not mutate the caller's args", () => {
		setPartnerCustomerProvider(() => "CUST-A");
		const args = { price_list: "X" };
		resolvePartnerCallArgs(ITEMS, args, config);
		expect(args).toEqual({ price_list: "X" });
	});

	it("says the call can't be made yet when no customer is chosen", () => {
		setPartnerCustomerProvider(() => null);
		expect(resolvePartnerCallArgs(ITEMS, { price_list: "X" }, config)).toBeNull();
	});

	it("is a no-op outside partner mode", () => {
		const args = { price_list: "X" };
		expect(resolvePartnerCallArgs(ITEMS, args, null)).toBe(args);
	});

	describe("through the installed guard", () => {
		let realCall: ReturnType<typeof vi.fn>;
		let realXcall: ReturnType<typeof vi.fn>;
		let stub: any;

		beforeEach(() => {
			realCall = vi.fn(() => Promise.resolve({ message: "real" }));
			realXcall = vi.fn(() => Promise.resolve("real"));
			stub = { boot: { posa_partner_mode: bootConfig() }, call: realCall, xcall: realXcall };
			(globalThis as any).frappe = stub;
			installPartnerCallGuard(stub);
		});

		it("adds the customer to an object-style call", async () => {
			setPartnerCustomerProvider(() => "CUST-A");
			await stub.call({ method: ITEMS, args: { price_list: "X" }, freeze: true });
			expect(realCall).toHaveBeenCalledWith({ method: ITEMS, args: { price_list: "X", customer: "CUST-A" }, freeze: true });
		});

		it("adds the customer to a string-style call, keeping the callback", async () => {
			setPartnerCustomerProvider(() => "CUST-A");
			const callback = vi.fn();
			await stub.call(ITEMS, { price_list: "X" }, callback);
			expect(realCall).toHaveBeenCalledWith(ITEMS, { price_list: "X", customer: "CUST-A" }, callback);
		});

		it("adds the customer to xcall", async () => {
			setPartnerCustomerProvider(() => "CUST-A");
			await stub.xcall(ITEMS, { price_list: "X" });
			expect(realXcall).toHaveBeenCalledWith(ITEMS, { price_list: "X", customer: "CUST-A" });
		});

		it("skips item calls quietly until a customer is chosen", async () => {
			setPartnerCustomerProvider(() => null);
			expect(await stub.call({ method: ITEMS, args: {} })).toEqual({ message: undefined });
			expect(await stub.xcall(ITEMS, {})).toBeUndefined();
			expect(realCall).not.toHaveBeenCalled();
			expect(realXcall).not.toHaveBeenCalled();
		});

		it("still passes calls that don't need a customer straight through", async () => {
			setPartnerCustomerProvider(() => null);
			await stub.call({ method: `${API}utils.get_active_pos_profile`, args: {} });
			expect(realCall).toHaveBeenCalledTimes(1);
		});
	});
});
