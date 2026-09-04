/**
 * Shared access to the deployed asset build descriptor.
 *
 * `version.json` is written by the Vite build (see `frontend/vite.config.js`)
 * and served as a plain static asset, so polling it costs the server nothing.
 * Both the service worker updater and the in-app update poller read it through
 * this module so they share a single short-lived cache.
 */

export interface BuildInfo {
	version: string | null;
	timestamp: number | null;
}

const VERSION_ENDPOINT = "/assets/posawesome/dist/js/version.json";
const VERSION_CACHE_TTL = 30 * 1000;

let cachedVersionInfo: BuildInfo | null = null;
let cachedVersionTimestamp = 0;
let pendingVersionRequest: Promise<BuildInfo | null> | null = null;

/** Seed the cache with a version already reported by the active service worker. */
export function primeBuildInfoCache(
	version: string | null,
	timestamp: number | null,
): void {
	if (!version || !timestamp) return;
	cachedVersionInfo = { version, timestamp };
	cachedVersionTimestamp = Date.now();
}

/** Drop the cached descriptor. Exposed for tests. */
export function resetBuildInfoCache(): void {
	cachedVersionInfo = null;
	cachedVersionTimestamp = 0;
	pendingVersionRequest = null;
}

export async function fetchBuildInfo(force = false): Promise<BuildInfo | null> {
	if (pendingVersionRequest) {
		return pendingVersionRequest;
	}
	const now = Date.now();
	if (
		!force &&
		cachedVersionInfo &&
		now - cachedVersionTimestamp < VERSION_CACHE_TTL
	) {
		return cachedVersionInfo;
	}
	pendingVersionRequest = (async () => {
		try {
			const response = await fetch(VERSION_ENDPOINT, {
				cache: "no-store",
				headers: {
					"Cache-Control": "no-cache",
					Pragma: "no-cache",
					Expires: "0",
				},
			});

			if (!response.ok) {
				return null;
			}
			const data: any = await response.json();
			const version = data.version || data.buildVersion || null;
			const timestamp = Number(data.timestamp || data.buildTimestamp);
			const parsed: BuildInfo = {
				version,
				timestamp: Number.isNaN(timestamp) ? null : timestamp,
			};
			cachedVersionInfo = parsed;
			cachedVersionTimestamp = Date.now();
			return parsed;
		} catch (err) {
			console.warn("Failed to fetch build info", err);
			return null;
		} finally {
			pendingVersionRequest = null;
		}
	})();
	return pendingVersionRequest;
}
