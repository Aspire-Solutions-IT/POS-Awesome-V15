// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { shallowMount } from "@vue/test-utils";

import NavbarMenu from "../src/posapp/components/navbar/NavbarMenu.vue";
import {
	ALL_POS_SCREENS,
	PROCESS_NOTES_METHOD,
	PROCESS_NOTES_UPDATED_EVENT,
	loadProcessNotes,
	notesForPosScreen,
	onProcessNotesUpdated,
	posScreenForRoute,
	resetProcessNotesCache,
} from "../src/posapp/utils/processNotes";

const flushPromises = () => new Promise((done) => setTimeout(done, 0));

const note = (name: string, links: any[], extra: Record<string, any> = {}) => ({
	name,
	title: `Note ${name}`,
	url: `https://workdrive.zoho.eu/${name}`,
	links,
	...extra,
});

const NOTES = [
	note("claims", [{ link_type: "POS Screen", pos_screen: "Customer Claims" }]),
	note("everywhere", [{ link_type: "POS Screen", pos_screen: ALL_POS_SCREENS }]),
	note("desk-only", [{ link_type: "Page", link_name: "posapp" }]),
	note("so-desk", [{ link_type: "DocType", link_name: "Sales Order", show_on: "Form and List" }]),
];

let realtimeHandlers: Record<string, () => void>;

const stubFrappe = (notes: any = NOTES) => {
	realtimeHandlers = {};
	const call = vi.fn(async ({ method }: { method: string }) => {
		if (method === PROCESS_NOTES_METHOD) {
			return { message: typeof notes === "function" ? notes() : notes };
		}
		return { message: {} };
	});
	vi.stubGlobal("frappe", {
		session: { user: "cashier@example.com", user_fullname: "Main Cashier" },
		boot: { pos_profile: {} },
		call,
		realtime: {
			on: (event: string, handler: () => void) => {
				realtimeHandlers[event] = handler;
			},
			off: vi.fn(),
		},
	});
	return call;
};

describe("process notes util", () => {
	beforeEach(() => {
		resetProcessNotesCache();
	});

	it("matches the current screen plus All Screens, ignoring desk links", () => {
		expect(notesForPosScreen(NOTES as any, "Customer Claims").map((n) => n.name)).toEqual([
			"claims",
			"everywhere",
		]);
		expect(notesForPosScreen(NOTES as any, "POS").map((n) => n.name)).toEqual(["everywhere"]);
		// Screens without a picker option (e.g. the dashboard) still get All Screens.
		expect(notesForPosScreen(NOTES as any, "").map((n) => n.name)).toEqual(["everywhere"]);
		expect(notesForPosScreen(null, "POS")).toEqual([]);
	});

	it("identifies the screen by the route title", () => {
		expect(posScreenForRoute({ meta: { title: "Customer Claims" } })).toBe("Customer Claims");
		expect(posScreenForRoute(undefined)).toBe("");
	});

	it("fetches once, and treats failures as no notes", async () => {
		const call = stubFrappe();
		await Promise.all([loadProcessNotes(), loadProcessNotes()]);
		await loadProcessNotes();
		expect(call).toHaveBeenCalledTimes(1);

		resetProcessNotesCache();
		vi.stubGlobal("frappe", { call: vi.fn(async () => Promise.reject(new Error("offline"))) });
		expect(await loadProcessNotes()).toEqual([]);
	});

	it("refetches when a note changes", async () => {
		let current: any[] = [];
		const call = stubFrappe(() => current);
		const received: any[] = [];
		onProcessNotesUpdated((notes) => received.push(notes));

		expect(await loadProcessNotes()).toEqual([]);
		current = NOTES;
		realtimeHandlers[PROCESS_NOTES_UPDATED_EVENT]();
		await flushPromises();

		expect(call).toHaveBeenCalledTimes(2);
		expect(received).toEqual([NOTES]);
	});
});

describe("NavbarMenu View Documents", () => {
	beforeEach(() => {
		resetProcessNotesCache();
		setActivePinia(createPinia());
		vi.stubGlobal("__", (value: string) => value);
	});

	const mountMenu = (routeTitle: string) =>
		shallowMount(NavbarMenu, {
			props: {
				posProfile: { name: "Main POS" },
				cashierName: "Main Cashier",
				manualOffline: false,
				networkOnline: true,
				serverOnline: true,
			},
			global: {
				mocks: {
					__: (value: string) => value,
					$theme: { isDark: { value: false } },
					$route: { meta: { title: routeTitle } },
				},
				stubs: {
					QzTrayDialog: true,
					ProcessNotesDialog: true,
					VMenu: true,
					VBtn: true,
					VIcon: true,
					VCard: true,
					VDialog: true,
					VSnackbar: true,
				},
			},
		});

	const quickActionIds = (wrapper: any) => wrapper.vm.quickActions.map((a: any) => a.id);

	it("adds View Documents for screens with notes and opens the dialog", async () => {
		stubFrappe();
		const wrapper = mountMenu("Customer Claims");
		await flushPromises();

		const action = (wrapper.vm as any).quickActions.find((a: any) => a.id === "process-notes");
		expect(action.label).toBe("View Documents");
		expect((wrapper.vm as any).screenProcessNotes.map((n: any) => n.name)).toEqual([
			"claims",
			"everywhere",
		]);

		(wrapper.vm as any).menuOpen = true;
		(wrapper.vm as any).handleAction(action);
		expect((wrapper.vm as any).showProcessNotesDialog).toBe(true);
		expect((wrapper.vm as any).menuOpen).toBe(false);
	});

	it("leaves the menu unchanged when the screen has no notes", async () => {
		stubFrappe([NOTES[0], NOTES[2]]);
		const wrapper = mountMenu("POS");
		await flushPromises();

		expect(quickActionIds(wrapper)).not.toContain("process-notes");
	});

	it("picks up notes added while the POS is open", async () => {
		let current: any[] = [];
		stubFrappe(() => current);
		const wrapper = mountMenu("POS");
		await flushPromises();
		expect(quickActionIds(wrapper)).not.toContain("process-notes");

		current = NOTES;
		realtimeHandlers[PROCESS_NOTES_UPDATED_EVENT]();
		await flushPromises();
		expect(quickActionIds(wrapper)).toContain("process-notes");
	});
});
