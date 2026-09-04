import { onBeforeUnmount, onMounted } from "vue";
import { useUpdateStore } from "../../stores/updateStore";

/**
 * Keeps long-lived POS tabs aware of newly deployed builds.
 *
 * A terminal is routinely left open across a nightly `bench update`, so the
 * update prompt cannot rely on a page load to notice a new build. This polls
 * the static build descriptor (`version.json`) hourly, plus whenever the tab is
 * brought back to the foreground or the connection returns — so a terminal that
 * is touched in the morning picks the overnight build up straight away. The
 * git-aware endpoint stays on a slower timer because it shells out to
 * `git fetch` on the server.
 */

/** How often an open tab re-reads the deployed build descriptor. */
const BUILD_POLL_INTERVAL_MS = 60 * 60 * 1000;
/** How often the server-side git comparison runs. */
const REMOTE_POLL_INTERVAL_MS = 24 * 60 * 60 * 1000;
const SERVICE_WORKER_SCOPE = "/sw.js";

export function useUpdatePolling(buildVersion: string | null = null) {
	const updateStore = useUpdateStore();
	let buildTimer: ReturnType<typeof setInterval> | null = null;
	let remoteTimer: ReturnType<typeof setInterval> | null = null;

	async function pingServiceWorker() {
		if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) {
			return;
		}
		try {
			const registration = await navigator.serviceWorker.getRegistration(
				SERVICE_WORKER_SCOPE,
			);
			await registration?.update();
		} catch (err) {
			console.warn("Failed to ask the service worker to check for updates", err);
		}
	}

	/**
	 * `includeRemote` also refreshes the commit details rendered in the prompt.
	 * That call runs `git fetch` server-side, so it is reserved for the slow
	 * timer and for the moment a genuinely new build is spotted.
	 */
	async function checkNow({ includeRemote = false, force = false } = {}) {
		if (typeof navigator !== "undefined" && navigator.onLine === false) {
			return;
		}
		let foundNewBuild = false;
		try {
			foundNewBuild = await updateStore.checkBuildVersion(force);
		} catch (err) {
			console.warn("Failed to check the deployed build version", err);
		}
		void pingServiceWorker();
		if (foundNewBuild || includeRemote) {
			await updateStore.checkForUpdates(true);
		}
	}

	function handleVisibilityChange() {
		if (document.visibilityState === "visible") {
			void checkNow();
		}
	}

	function handleOnline() {
		void checkNow();
	}

	/**
	 * Without a service worker — plain http:// origins, unsupported browsers —
	 * nothing registers a reload action, which leaves "Reload Now" inert.
	 */
	function ensureReloadFallback() {
		if (typeof updateStore.reloadAction === "function") return;
		updateStore.setReloadAction(() => window.location.reload());
	}

	onMounted(() => {
		updateStore.initializeFromStorage();
		if (buildVersion) {
			updateStore.setCurrentVersion(buildVersion);
		}
		ensureReloadFallback();
		void checkNow({ includeRemote: true, force: true });
		buildTimer = setInterval(() => void checkNow(), BUILD_POLL_INTERVAL_MS);
		remoteTimer = setInterval(
			() => void checkNow({ includeRemote: true }),
			REMOTE_POLL_INTERVAL_MS,
		);
		document.addEventListener("visibilitychange", handleVisibilityChange);
		window.addEventListener("online", handleOnline);
	});

	onBeforeUnmount(() => {
		if (buildTimer) {
			clearInterval(buildTimer);
			buildTimer = null;
		}
		if (remoteTimer) {
			clearInterval(remoteTimer);
			remoteTimer = null;
		}
		document.removeEventListener("visibilitychange", handleVisibilityChange);
		window.removeEventListener("online", handleOnline);
	});

	return { checkNow };
}
