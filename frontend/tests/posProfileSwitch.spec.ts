// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

const offlineMocks = vi.hoisted(() => ({
	initPromise: Promise.resolve(),
	checkDbHealth: vi.fn().mockResolvedValue(true),
	getOpeningStorage: vi.fn().mockReturnValue(null),
	setOpeningStorage: vi.fn(),
	clearOpeningStorage: vi.fn(),
	setTaxTemplate: vi.fn(),
	isOffline: vi.fn().mockReturnValue(false),
	getBootstrapSnapshot: vi.fn().mockReturnValue(null),
	setBootstrapSnapshot: vi.fn(),
	getPendingOfflineInvoiceCount: vi.fn().mockReturnValue(0),
}));

vi.mock("../src/offline/index", () => offlineMocks);
vi.mock("../src/offline/bootstrapSnapshot", () => ({
	createBootstrapSnapshotFromRegisterData: vi.fn().mockReturnValue({}),
}));

import { usePosShift, reloadTerminal } from "../src/posapp/composables/pos/shared/usePosShift";
import {
	ACTIVE_OPENING_SHIFT_KEY,
	getValidCachedOpeningForCurrentUser,
	setActiveOpeningShiftName,
} from "../src/posapp/utils/openingCache";

const REGISTER_DATA = {
	pos_profile: { name: "POS-B", currency: "GBP" },
	pos_opening_shift: { name: "SHIFT-B", user: "cashier@example.com" },
	company: { name: "Test Co" },
	stock_settings: { allow_negative_stock: false },
};

let reloadSpy = vi.fn();

function stubLocationReload(reload: () => void) {
	Object.defineProperty(window, "location", {
		configurable: true,
		writable: true,
		value: { ...window.location, reload },
	});
}

function stubFrappe(callImpl: any) {
	const frappeStub = {
		session: { user: "cashier@example.com" },
		call: vi.fn(callImpl),
		realtime: { emit: vi.fn() },
	};
	vi.stubGlobal("frappe", frappeStub);
	return frappeStub;
}

describe("POS profile switching", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.clearAllMocks();
		localStorage.clear();
		offlineMocks.isOffline.mockReturnValue(false);
		offlineMocks.getPendingOfflineInvoiceCount.mockReturnValue(0);
		(window as any).__ = (value: string) => value;
		reloadSpy = vi.fn();
		stubLocationReload(reloadSpy);
	});

	it("refuses to switch while offline", async () => {
		const frappeStub = stubFrappe(() => Promise.resolve({ message: REGISTER_DATA }));
		offlineMocks.isOffline.mockReturnValue(true);

		const { switch_pos_profile } = usePosShift();
		const result = await switch_pos_profile({ target_profile: "POS-B" });

		expect(result).toEqual({ success: false, reason: "offline" });
		expect(frappeStub.call).not.toHaveBeenCalled();
	});

	it("refuses to switch while offline sales are still pending sync", async () => {
		const frappeStub = stubFrappe(() => Promise.resolve({ message: REGISTER_DATA }));
		offlineMocks.getPendingOfflineInvoiceCount.mockReturnValue(3);

		const { switch_pos_profile } = usePosShift();
		const result = await switch_pos_profile({ target_profile: "POS-B" });

		expect(result).toEqual({ success: false, reason: "pending_invoices" });
		expect(frappeStub.call).not.toHaveBeenCalled();
	});

	it("primes the caches and pins the new shift on a successful switch", async () => {
		const frappeStub = stubFrappe(() => Promise.resolve({ message: REGISTER_DATA }));

		const { switch_pos_profile } = usePosShift();
		const result = await switch_pos_profile({
			target_profile: "POS-B",
			supervisor_user: "supervisor@example.com",
			pin: "1234",
		});

		expect(result.success).toBe(true);
		expect(frappeStub.call).toHaveBeenCalledWith(
			"posawesome.posawesome.api.shifts.switch_pos_profile",
			expect.objectContaining({
				target_profile: "POS-B",
				supervisor_user: "supervisor@example.com",
				pin: "1234",
			}),
		);
		expect(offlineMocks.setOpeningStorage).toHaveBeenCalledWith(REGISTER_DATA);
		expect(localStorage.getItem(ACTIVE_OPENING_SHIFT_KEY)).toBe("SHIFT-B");
		expect(reloadSpy).toHaveBeenCalled();
	});

	it("asks the server for the shift the terminal was last operating", async () => {
		const frappeStub = stubFrappe(() => Promise.resolve({ message: REGISTER_DATA }));
		setActiveOpeningShiftName("SHIFT-A");

		const { check_opening_entry } = usePosShift();
		await check_opening_entry();

		expect(frappeStub.call).toHaveBeenCalledWith(
			"posawesome.posawesome.api.shifts.check_opening_shift",
			{ user: "cashier@example.com", preferred_shift: "SHIFT-A" },
		);
	});
});

describe("opening cache validity across parallel shifts", () => {
	beforeEach(() => {
		localStorage.clear();
	});

	it("accepts a cached opening that matches the active shift", () => {
		setActiveOpeningShiftName("SHIFT-B");
		expect(
			getValidCachedOpeningForCurrentUser(REGISTER_DATA, "cashier@example.com"),
		).toBe(REGISTER_DATA);
	});

	it("rejects a cached opening left behind by a profile the cashier switched away from", () => {
		setActiveOpeningShiftName("SHIFT-A");
		expect(
			getValidCachedOpeningForCurrentUser(REGISTER_DATA, "cashier@example.com"),
		).toBeNull();
	});

	it("still rejects a cached opening belonging to another user", () => {
		setActiveOpeningShiftName("SHIFT-B");
		expect(
			getValidCachedOpeningForCurrentUser(REGISTER_DATA, "someone@example.com"),
		).toBeNull();
	});

	it("falls back to the cache when no active shift is pinned", () => {
		expect(
			getValidCachedOpeningForCurrentUser(REGISTER_DATA, "cashier@example.com"),
		).toBe(REGISTER_DATA);
	});
});

describe("reloadTerminal", () => {
	it("swallows reload failures rather than breaking the switch", () => {
		stubLocationReload(() => {
			throw new Error("denied");
		});
		expect(() => reloadTerminal()).not.toThrow();
	});
});
