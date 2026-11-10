// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useEmployeeStore } from "../src/posapp/stores/employeeStore";

describe("employeeStore", () => {
	beforeEach(() => {
		localStorage.clear();
		setActivePinia(createPinia());
		(globalThis as any).frappe = {
			session: {
				user: "cashier@example.com",
				user_fullname: "Main Cashier",
			},
		};
	});

	it("defaults current cashier from session and supports cashier switching", () => {
		const store = useEmployeeStore();

		store.setTerminalEmployees([
			{
				user: "cashier@example.com",
				full_name: "Main Cashier",
			},
			{
				user: "backup@example.com",
				full_name: "Backup Cashier",
			},
		]);

		expect(store.currentCashier?.user).toBe("cashier@example.com");
		expect(store.currentCashierDisplay).toBe("Main Cashier");

		store.setCurrentCashier("backup@example.com");

		expect(store.currentCashier?.user).toBe("backup@example.com");
		expect(store.currentCashierDisplay).toBe("Backup Cashier");
	});

	it("opens switch flow and locks or unlocks the terminal", () => {
		const store = useEmployeeStore();

		store.openEmployeeSwitch();
		expect(store.switchDialogOpen).toBe(true);

		store.lockTerminal();
		expect(store.switchDialogOpen).toBe(false);
		expect(store.lockDialogOpen).toBe(true);
		expect(store.isLocked).toBe(true);

		store.unlockTerminal();
		expect(store.lockDialogOpen).toBe(false);
		expect(store.isLocked).toBe(false);
	});

	it("keeps the lock state across a page refresh", () => {
		const store = useEmployeeStore();
		expect(store.isLocked).toBe(false);

		store.lockTerminal();
		setActivePinia(createPinia());
		expect(useEmployeeStore().isLocked).toBe(true);

		useEmployeeStore().unlockTerminal();
		setActivePinia(createPinia());
		expect(useEmployeeStore().isLocked).toBe(false);
	});

	it("upgrades the session cashier with supervisor metadata from terminal employees", () => {
		const store = useEmployeeStore();

		expect(store.currentCashier?.user).toBe("cashier@example.com");
		expect(store.currentCashier?.is_supervisor).toBeUndefined();

		store.setTerminalEmployees([
			{
				user: "cashier@example.com",
				full_name: "Main Cashier",
				is_supervisor: true,
			},
		]);

		expect(store.currentCashier?.user).toBe("cashier@example.com");
		expect(store.currentCashier?.is_supervisor).toBe(true);
	});
});

describe("employeeStore for a Sales Partner", () => {
	const asPartner = () => {
		(globalThis as any).frappe = {
			session: { user: "partner@example.com", user_fullname: "Partner" },
			boot: { posa_partner_mode: { partners: ["SP-A"], allowed_methods: [] } },
		};
	};

	beforeEach(() => {
		localStorage.clear();
		setActivePinia(createPinia());
		asPartner();
	});

	it("cannot lock the terminal until they have a PIN to unlock with", () => {
		const store = useEmployeeStore();

		expect(store.partnerHasPin).toBeNull();
		expect(store.canLockTerminal).toBe(false);
		store.lockTerminal();
		expect(store.isLocked).toBe(false);

		store.setPartnerHasPin(false);
		store.lockTerminal();
		expect(store.isLocked).toBe(false);
	});

	it("can lock once a PIN exists, and unlock again", () => {
		const store = useEmployeeStore();
		store.setPartnerHasPin(true);

		expect(store.canLockTerminal).toBe(true);
		store.lockTerminal();
		expect(store.isLocked).toBe(true);

		store.unlockTerminal();
		expect(store.isLocked).toBe(false);
	});

	it("is offered only themselves", () => {
		const store = useEmployeeStore();
		store.setTerminalEmployees([{ user: "partner@example.com", full_name: "Partner", is_current: true }]);

		expect(store.terminalEmployees.map((employee) => employee.user)).toEqual(["partner@example.com"]);
		expect(store.currentCashier?.user).toBe("partner@example.com");
	});

	it("leaves staff terminals exactly as they were", () => {
		(globalThis as any).frappe = { session: { user: "cashier@example.com" }, boot: {} };
		const store = useEmployeeStore();

		expect(store.canLockTerminal).toBe(true);
		store.lockTerminal();
		expect(store.isLocked).toBe(true);
	});
});
