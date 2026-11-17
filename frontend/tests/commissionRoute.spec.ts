// @vitest-environment jsdom

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../src/posapp/composables/core/useLoading", () => ({
	startRouteLoading: vi.fn(),
	stopRouteLoading: vi.fn(),
}));

import { createPosAppRouter } from "../src/posapp/router";

describe("commission route for sales partners", () => {
	beforeEach(() => {
		(globalThis as any).frappe = {
			boot: { posa_partner_mode: { partners: ["P"], allowed_methods: [] } },
		};
	});
	afterEach(() => {
		window.history.replaceState({}, "", "/");
	});

	it("lets a partner open /commission instead of bouncing them to the POS", async () => {
		const { router } = createPosAppRouter();
		await router.push("/commission");
		await router.isReady();

		expect(router.currentRoute.value.path).toBe("/commission");
		expect(router.currentRoute.value.meta.title).toBe("My Commission");
	});
});
