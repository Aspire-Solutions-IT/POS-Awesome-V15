// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { mount } from "@vue/test-utils";
import { defineComponent, h } from "vue";

import { useEmployeeStore } from "../src/posapp/stores/employeeStore";
import { useInactivityLock } from "../src/posapp/composables/core/useInactivityLock";

const TIMEOUT_MS = 5 * 60 * 1000;
const CHECK_MS = 10_000;

// Mirrors how DefaultLayout wires the lock: enabled once a profile is registered and the
// terminal can actually be locked (a Sales Partner needs a PIN first).
const mountLockedWhenIdle = () => {
	const store = useEmployeeStore();
	const Host = defineComponent({
		setup() {
			useInactivityLock(TIMEOUT_MS, () => store.canLockTerminal);
			return () => h("div");
		},
	});
	return { store, wrapper: mount(Host) };
};

const asPartner = () => {
	(globalThis as any).frappe = {
		session: { user: "partner@example.com" },
		boot: { posa_partner_mode: { partners: ["SP-A"], allowed_methods: [] } },
	};
};

describe("terminal auto-lock after five minutes of inactivity", () => {
	beforeEach(() => {
		vi.useFakeTimers();
		localStorage.clear();
		setActivePinia(createPinia());
		(globalThis as any).frappe = { session: { user: "cashier@example.com" }, boot: {} };
	});

	afterEach(() => {
		vi.useRealTimers();
		delete (globalThis as any).frappe;
	});

	it("locks a staff terminal once the timeout passes", () => {
		const { store, wrapper } = mountLockedWhenIdle();
		vi.advanceTimersByTime(TIMEOUT_MS - CHECK_MS);
		expect(store.isLocked).toBe(false);
		vi.advanceTimersByTime(CHECK_MS * 2);
		expect(store.isLocked).toBe(true);
		wrapper.unmount();
	});

	it("locks a Sales Partner who has a PIN", () => {
		asPartner();
		const { store, wrapper } = mountLockedWhenIdle();
		store.setPartnerHasPin(true);
		vi.advanceTimersByTime(TIMEOUT_MS + CHECK_MS);
		expect(store.isLocked).toBe(true);
		wrapper.unmount();
	});

	it("never locks a Sales Partner who has no PIN (they could not get back in)", () => {
		asPartner();
		const { store, wrapper } = mountLockedWhenIdle();
		store.setPartnerHasPin(false);
		vi.advanceTimersByTime(TIMEOUT_MS * 3);
		expect(store.isLocked).toBe(false);
		wrapper.unmount();
	});

	it("starts locking a partner once they create their PIN", () => {
		asPartner();
		const { store, wrapper } = mountLockedWhenIdle();
		store.setPartnerHasPin(false);
		vi.advanceTimersByTime(TIMEOUT_MS * 2);
		expect(store.isLocked).toBe(false);

		store.setPartnerHasPin(true);
		vi.advanceTimersByTime(CHECK_MS);
		expect(store.isLocked).toBe(true);
		wrapper.unmount();
	});

	it("counts activity: a busy partner is not locked", () => {
		asPartner();
		const { store, wrapper } = mountLockedWhenIdle();
		store.setPartnerHasPin(true);
		for (let i = 0; i < 6; i++) {
			vi.advanceTimersByTime(TIMEOUT_MS / 2);
			window.dispatchEvent(new Event("mousemove"));
		}
		expect(store.isLocked).toBe(false);
		wrapper.unmount();
	});
});
