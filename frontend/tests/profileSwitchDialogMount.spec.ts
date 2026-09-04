// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { shallowMount } from "@vue/test-utils";

vi.mock("../src/offline/index", () => ({
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
vi.mock("../src/offline/bootstrapSnapshot", () => ({
	createBootstrapSnapshotFromRegisterData: vi.fn().mockReturnValue({}),
}));

import ProfileSwitchDialog from "../src/posapp/components/pos/shift/ProfileSwitchDialog.vue";

describe("ProfileSwitchDialog mounts without looping", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.stubGlobal("__", (value: string) => value);
		vi.stubGlobal("frappe", {
			session: { user: "cashier@example.com", user_fullname: "Main Cashier" },
			call: vi.fn(async () => ({ message: { pos_profiles_data: [], payments_method: [] } })),
		});
	});

	it("mounts closed without runaway renders", async () => {
		const errors: any[] = [];
		const warns: any[] = [];
		vi.spyOn(console, "error").mockImplementation((...a) => errors.push(a.join(" ")));
		vi.spyOn(console, "warn").mockImplementation((...a) => warns.push(a.join(" ")));

		const wrapper = shallowMount(ProfileSwitchDialog, {
			props: { modelValue: false },
			global: { mocks: { __: (v: string) => v }, provide: { eventBus: { on: vi.fn(), emit: vi.fn() } } },
		});

		await Promise.resolve();
		await Promise.resolve();

		const noisy = [...errors, ...warns].filter((m) =>
			/recursive|maximum|infinite/i.test(m),
		);
		expect(noisy).toEqual([]);
		expect(wrapper.exists()).toBe(true);
	});

	// DefaultLayout renders this behind v-if, so it mounts already-open. It must not
	// need frappe.datetime to do that: invoiceStore reads it at construction, and
	// touching that store during boot is what stalled the whole app.
	it("mounts already-open and loads profiles without frappe.datetime", async () => {
		expect((globalThis as any).frappe.datetime).toBeUndefined();

		const wrapper = shallowMount(ProfileSwitchDialog, {
			props: { modelValue: true },
			global: { mocks: { __: (v: string) => v }, provide: { eventBus: { on: vi.fn(), emit: vi.fn() } } },
		});

		await Promise.resolve();
		await Promise.resolve();

		expect(wrapper.exists()).toBe(true);
		expect((globalThis as any).frappe.call).toHaveBeenCalledWith(
			"posawesome.posawesome.api.shifts.get_switchable_pos_profiles",
		);
	});
});
