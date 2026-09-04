// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import { useUpdateStore } from "../src/posapp/stores/updateStore";
import { resetBuildInfoCache } from "../src/posapp/utils/buildInfo";

function mockVersionEndpoint(version: string, timestamp: number) {
	const fetchMock = vi.fn().mockResolvedValue({
		ok: true,
		json: async () => ({ version, timestamp }),
	});
	vi.stubGlobal("fetch", fetchMock);
	return fetchMock;
}

describe("build version polling", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		resetBuildInfoCache();
		window.localStorage.clear();
		window.sessionStorage.clear();
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it("prompts when a tab left open sees a newly deployed build", async () => {
		const store = useUpdateStore();
		store.setCurrentVersion("build-1000", 1000);
		expect(store.shouldPrompt).toBe(false);

		mockVersionEndpoint("build-2000", 2000);
		await expect(store.checkBuildVersion(true)).resolves.toBe(true);

		expect(store.availableVersion).toBe("build-2000");
		expect(store.shouldPrompt).toBe(true);
	});

	it("stays quiet while the deployed build is unchanged", async () => {
		const store = useUpdateStore();
		store.setCurrentVersion("build-1000", 1000);

		mockVersionEndpoint("build-1000", 1000);
		await expect(store.checkBuildVersion(true)).resolves.toBe(false);

		expect(store.shouldPrompt).toBe(false);
	});

	it("reads the build descriptor without hitting the HTTP cache", async () => {
		const store = useUpdateStore();
		const fetchMock = mockVersionEndpoint("build-2000", 2000);
		await store.checkBuildVersion(true);

		const [url, init] = fetchMock.mock.calls[0];
		expect(url).toBe("/assets/posawesome/dist/js/version.json");
		expect(init.cache).toBe("no-store");
	});

	it("keeps a failed check from clearing the known version", async () => {
		const store = useUpdateStore();
		store.setCurrentVersion("build-1000", 1000);
		vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
		vi.spyOn(console, "warn").mockImplementation(() => {});

		await expect(store.checkBuildVersion(true)).resolves.toBe(false);
		expect(store.availableVersion).toBe("build-1000");
		expect(store.shouldPrompt).toBe(false);
	});

	it("does not prompt for remote commits that are not deployed here yet", async () => {
		const store = useUpdateStore();
		store.setCurrentVersion("build-1000", 1000);

		vi.stubGlobal("frappe", {
			call: vi.fn().mockResolvedValue({
				message: {
					build_version: "build-1000",
					commit_hash: "local-sha",
					current_branch: "main",
					remote_ahead: { main: "remote-sha" },
					remote_sample_branch: "main",
					remote_sample: {
						commit_hash: "remote-sha",
						commit_message: "upstream work",
						commit_date: "2026-08-26 01:00:00",
					},
					remote_commits: [
						{ commit_hash: "remote-sha", commit_short: "remote" },
					],
				},
			}),
		});

		await store.checkForUpdates(true);

		// The commits are surfaced as detail, but reloading the tab cannot apply
		// code that has not been pulled and built on this bench yet.
		expect(store.availableBranch).toBe("main");
		expect(store.availableCommits).toHaveLength(1);
		expect(store.availableVersion).toBe("build-1000");
		expect(store.shouldPrompt).toBe(false);
	});
});
