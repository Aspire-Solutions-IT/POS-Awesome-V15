import { defineStore } from "pinia";
import { ref, computed } from "vue";

declare const frappe: any;
declare const __: any;
import type { Customer, POSProfile } from "../types/models";
// @ts-ignore
import {
	db,
	checkDbHealth,
	setCustomerStorage,
	saveStoredValueSnapshot,
	memoryInitPromise,
	getCustomersLastSync,
	setCustomersLastSync,
	getCustomerStorageCount,
	clearCustomerStorage,
	isOffline,
	refreshBootstrapSnapshotFromCacheState,
} from "../../offline/index";

const PAGE_SIZE = 1000;
const CUSTOMER_SCOPE_STORAGE_KEY = "posa_customers_profile_scope";
const EXCLUDED_CUSTOMER_NAMES = new Set(["13682"]);

function isCustomerVisible(customer: Pick<Customer, "name"> | null | undefined): boolean {
	return !EXCLUDED_CUSTOMER_NAMES.has(String(customer?.name || "").trim());
}

function getCustomerProfileScope(profile: POSProfile | null): string {
	const profileName =
		typeof profile?.name === "string" ? profile.name.trim() : "";
	return profileName || "";
}

function getStoredCustomerScope(): string {
	if (typeof localStorage === "undefined") {
		return "";
	}
	const stored = localStorage.getItem(CUSTOMER_SCOPE_STORAGE_KEY);
	return typeof stored === "string" ? stored : "";
}

function setStoredCustomerScope(scope: string): void {
	if (typeof localStorage === "undefined") {
		return;
	}
	if (scope) {
		localStorage.setItem(CUSTOMER_SCOPE_STORAGE_KEY, scope);
		return;
	}
	localStorage.removeItem(CUSTOMER_SCOPE_STORAGE_KEY);
}

function normalizeSearchTerm(term: string | null | undefined): string {
	if (typeof term !== "string") {
		return "";
	}
	return term.trim();
}

function normalizeProfile(profile: any): POSProfile | null {
	if (!profile) {
		return null;
	}

	let resolved = profile;

	if (profile.pos_profile) {
		resolved = profile.pos_profile;
	}

	if (typeof resolved === "string") {
		const trimmed = resolved.trim();
		if (!trimmed) {
			return null;
		}

		if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
			try {
				return JSON.parse(trimmed);
			} catch (err) {
				console.error("Failed to parse POS profile JSON", err);
				return null;
			}
		}

		return { name: trimmed } as POSProfile;
	}

	return resolved as POSProfile;
}

function getSerializedProfile(profile: any): string | null {
	if (!profile) {
		return null;
	}

	if (typeof profile === "string") {
		const trimmed = profile.trim();
		if (!trimmed) {
			return null;
		}
		if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
			return trimmed;
		}
		return JSON.stringify({ name: trimmed });
	}

	let fallbackName = null;
	if (typeof profile === "object" && profile !== null) {
		if (typeof profile.name === "string") {
			fallbackName = profile.name;
		} else if (typeof profile.pos_profile === "string") {
			fallbackName = profile.pos_profile;
		} else if (profile.pos_profile?.name) {
			fallbackName = profile.pos_profile.name;
		}
	}

	try {
		return JSON.stringify(profile);
	} catch (err) {
		console.error("Failed to serialize POS profile", err);
		if (fallbackName) {
			return JSON.stringify({ name: fallbackName });
		}
		return null;
	}
}

export const useCustomersStore = defineStore("customers", () => {
	const customers = ref<Customer[]>([]);
	const selectedCustomer = ref<string | null>(null);
	const customerInfo = ref<Record<string, any>>({});
	const searchTerm = ref("");
	const page = ref(0);
	const hasMore = ref(true);
	const nextCustomerStart = ref<string | null>(null);
	const loadingCustomers = ref(false);
	const customersLoaded = ref(false);
	const isCustomerBackgroundLoading = ref(false);
	const pendingCustomerSearch = ref<string | null>(null);
	const loadProgress = ref(0);
	const totalCustomerCount = ref(0);
	const loadedCustomerCount = ref(0);
	const posProfile = ref<POSProfile | null>(null);
	const customerProfileScope = ref("");
	const refreshToken = ref(0);
	const isUpdateCustomerDialogOpen = ref(false);
	const customerToUpdate = ref<Customer | null>(null);
	let customerFetchPromise: Promise<void> | null = null;
	const customerLoadLogState = {
		local: false,
		server: false,
		final: false,
	};

	function resetCustomerLoadLogState() {
		customerLoadLogState.local = false;
		customerLoadLogState.server = false;
		customerLoadLogState.final = false;
	}

	function logLocalCustomerCount(count: number) {
		if (customerLoadLogState.local) return;
		console.log(`Local customer count: ${count}`);
		customerLoadLogState.local = true;
	}

	function logServerCustomerCount(count: number) {
		if (customerLoadLogState.server) return;
		console.log(`Server customer count: ${count}`);
		customerLoadLogState.server = true;
	}

	function logFinalLoadedCustomerCount() {
		if (customerLoadLogState.final) return;
		const count = Number(loadedCustomerCount.value || customers.value.length || 0);
		console.log(`Customers loaded: ${count}`);
		customerLoadLogState.final = true;
	}

	const filteredCustomers = computed(() =>
		customers.value.filter((customer) => isCustomerVisible(customer)),
	);

	const isLoadComplete = computed(
		() => customersLoaded.value && loadProgress.value >= 100,
	);

	async function ensureDatabase() {
		await memoryInitPromise;
		await checkDbHealth();
		if (!db.isOpen()) {
			await db.open();
		}
	}

	function resetPagination() {
		page.value = 0;
		hasMore.value = true;
		customers.value = [];
	}

	function setPosProfile(profile: any) {
		posProfile.value = normalizeProfile(profile);
		customerProfileScope.value = getCustomerProfileScope(posProfile.value);
	}

	function setSelectedCustomer(name: string | null) {
		selectedCustomer.value = name || null;
	}

	function setCustomerInfo(info: Record<string, any>) {
		customerInfo.value = info || {};
		if (info?.name) {
			void setCustomerStorage([info]);
		}
		if (
			info?.name &&
			posProfile.value?.company &&
			typeof info?.stored_value_balance !== "undefined"
		) {
			const totalCredit = Number(info.stored_value_balance || 0);
			saveStoredValueSnapshot(info.name, posProfile.value.company, totalCredit > 0 ? [
				{
					type: "Snapshot",
					credit_origin: "offline-customer-cache",
					total_credit: totalCredit,
					source_type: "Stored Value Snapshot",
				},
			] : []);
		}
	}

	function requestCustomerRefresh() {
		refreshToken.value += 1;
	}

	function syncBootstrapCustomerReadiness(count: number | boolean) {
		refreshBootstrapSnapshotFromCacheState({
			customersCount: count,
		});
	}

	async function ensureCustomerScopeIsolation() {
		const currentScope =
			customerProfileScope.value || getCustomerProfileScope(posProfile.value);
		if (!currentScope) {
			return;
		}

		const storedScope = getStoredCustomerScope();
		if (storedScope === currentScope) {
			return;
		}

		await clearCustomerStorage();
		setCustomersLastSync(null);
		setStoredCustomerScope(currentScope);
		resetPagination();
		customersLoaded.value = false;
		loadProgress.value = 0;
		totalCustomerCount.value = 0;
		loadedCustomerCount.value = 0;
		nextCustomerStart.value = null;
		syncBootstrapCustomerReadiness(0);
	}

	async function searchCustomersOnServer(term: string): Promise<Customer[]> {
		if (!posProfile.value || isOffline()) {
			return [];
		}
		const serializedProfile = getSerializedProfile(posProfile.value);
		if (!serializedProfile) {
			return [];
		}
		try {
			const response = await (frappe.call as any)({
				method: "posawesome.posawesome.api.customers.search_customers",
				args: { pos_profile: serializedProfile, term, limit: 50 },
			});
			const rows: Customer[] = (response?.message || []).filter(
				(customer: Customer) => isCustomerVisible(customer),
			);
			if (rows.length) {
				// Cache the hit so the next search resolves locally, and flag
				// the cache as short so the next verify pass repairs it.
				await setCustomerStorage(rows);
				console.warn(
					`Customer "${term}" was missing from the local cache; served ${rows.length} row(s) from the server`,
				);
			}
			return rows;
		} catch (err) {
			console.error("Server customer search failed", err);
			return [];
		}
	}

	async function performSearch({ append = false } = {}) {
		await ensureDatabase();

		let collection = db.table("customers");
		const normalizedTerm = normalizeSearchTerm(searchTerm.value);
		if (normalizedTerm) {
			const searchParts = normalizedTerm
				.toLowerCase()
				.split(/\s+/)
				.filter(Boolean);
			collection = collection.filter((customer: Customer) => {
				if (!customer) {
					return false;
				}

				const values = [
					customer.customer_name,
					customer.name,
					customer.mobile_no,
					customer.email_id,
					customer.tax_id,
				]
					.filter((value) => value !== null && value !== undefined)
					.map((value) => String(value).toLowerCase());

				if (!searchParts.length) {
					return true;
				}

				return searchParts.every((part) =>
					values.some((value) => value.includes(part)),
				);
			});
		}

		const offset = page.value * PAGE_SIZE;
		const results = await collection
			.offset(offset)
			.limit(PAGE_SIZE)
			.toArray();
		const visibleResults = results.filter((customer) => isCustomerVisible(customer));

		if (append) {
			customers.value = [...customers.value, ...visibleResults];
		} else {
			customers.value = visibleResults;
		}

		// The local cache can be stale or incomplete. Rather than telling the
		// operator a customer does not exist, ask the server before giving up.
		if (!append && normalizedTerm && !visibleResults.length) {
			const remote = await searchCustomersOnServer(normalizedTerm);
			if (remote.length) {
				customers.value = remote;
				hasMore.value = false;
				return remote.length;
			}
		}

		hasMore.value = results.length === PAGE_SIZE;
		if (hasMore.value) {
			page.value += 1;
		}

		return visibleResults.length;
	}

	async function searchCustomers(term = "", append = false) {
		if (!append) {
			searchTerm.value = normalizeSearchTerm(term);
			resetPagination();
		}
		return performSearch({ append });
	}

	async function queueSearch(term: string) {
		const normalized = normalizeSearchTerm(term);
		if (isCustomerBackgroundLoading.value) {
			pendingCustomerSearch.value = normalized;
			return null;
		}
		return searchCustomers(normalized, false);
	}

	async function loadMoreCustomers() {
		if (loadingCustomers.value) {
			return 0;
		}
		const count = await performSearch({ append: true });
		if (count === PAGE_SIZE) {
			return count;
		}
		if (nextCustomerStart.value) {
			await backgroundLoadCustomers(nextCustomerStart.value);
			await performSearch({ append: true });
		}
		return count;
	}

	function fetchCustomerPage(
		startAfter: string | null,
		modifiedAfter: string | null,
		limit: number,
	): Promise<Customer[]> {
		const serializedProfile = getSerializedProfile(posProfile.value);
		return new Promise((resolve, reject) => {
			if (!serializedProfile) {
				resolve([]);
				return;
			}
			frappe.call({
				method: "posawesome.posawesome.api.customers.get_customer_names",
				args: {
					pos_profile: serializedProfile,
					modified_after: modifiedAfter,
					limit,
					start_after: startAfter,
				},
				callback: (r: any) => resolve(r.message || []),
				error: (err: any) => {
					console.error("Failed to fetch customers", err);
					reject(err);
				},
			});
		});
	}

	// Stamp the sync watermark only once the cache actually matches the server.
	// Stamping over a short cache strands every missing row behind it: those rows
	// have an older `modified` than the watermark, so no delta fetch can reach
	// them and the gap becomes permanent.
	async function finalizeCustomerSync(): Promise<boolean> {
		const localCount = await getCustomerStorageCount();
		loadedCustomerCount.value = localCount;
		syncBootstrapCustomerReadiness(localCount);
		customersLoaded.value = true;

		const expected = Number(totalCustomerCount.value || 0);
		if (expected && localCount < expected) {
			console.warn(
				`Customer cache incomplete: ${localCount} of ${expected} cached; watermark not advanced`,
			);
			loadProgress.value = Math.min(
				99,
				Math.round((localCount / expected) * 100),
			);
			return false;
		}

		setCustomersLastSync(new Date().toISOString());
		loadProgress.value = 100;
		logFinalLoadedCustomerCount();
		return true;
	}

	// Drop the cache and reload it from scratch. This is the only way to recover
	// rows that are older than the current watermark.
	async function fullResyncCustomers(expectedCount = 0) {
		await clearCustomerStorage();
		setCustomersLastSync(null);
		resetPagination();
		loadedCustomerCount.value = 0;
		nextCustomerStart.value = null;
		if (expectedCount) {
			totalCustomerCount.value = expectedCount;
		}
		syncBootstrapCustomerReadiness(0);

		const rows: Customer[] = await fetchCustomerPage(null, null, PAGE_SIZE);
		if (rows.length) {
			await setCustomerStorage(rows);
		}
		loadedCustomerCount.value = rows.length;

		const startAfter =
			rows.length === PAGE_SIZE ? rows[rows.length - 1]?.name || null : null;
		if (startAfter) {
			nextCustomerStart.value = startAfter;
			await backgroundLoadCustomers(startAfter);
		} else {
			await finalizeCustomerSync();
		}
	}

	async function backgroundLoadCustomers(
		startAfter: string | null,
		_syncSince: string | null = null,
	) {
		if (!posProfile.value || isOffline()) {
			return;
		}
		const serializedProfile = getSerializedProfile(posProfile.value);
		if (!serializedProfile) {
			return;
		}
		const limit = PAGE_SIZE;
		isCustomerBackgroundLoading.value = true;
		try {
			let cursor: string | null = startAfter;
			while (cursor) {
				// Backfill pages must not carry modified_after. Combining a
				// cursor with a delta filter returns an empty page, which the
				// loop below would read as "end of list" and truncate the sync.
				const rows: Customer[] = await fetchCustomerPage(
					cursor,
					null,
					limit,
				);
				if (rows.length) {
					await setCustomerStorage(rows);
					loadedCustomerCount.value += rows.length;
					syncBootstrapCustomerReadiness(loadedCustomerCount.value);
					if (totalCustomerCount.value) {
						const progress = Math.min(
							100,
							Math.round(
								(loadedCustomerCount.value /
									totalCustomerCount.value) *
									100,
							),
						);
						loadProgress.value = progress;
					}
				}
				if (rows.length === limit) {
					cursor = rows[rows.length - 1]?.name || null;
					nextCustomerStart.value = cursor;
				} else {
					cursor = null;
					nextCustomerStart.value = null;
					await finalizeCustomerSync();
				}
			}
		} catch (err) {
			console.error("Failed to background load customers", err);
		} finally {
			isCustomerBackgroundLoading.value = false;
			if (
				!nextCustomerStart.value &&
				customersLoaded.value &&
				loadProgress.value >= 99
			) {
				loadProgress.value = 100;
			}
			if (pendingCustomerSearch.value !== null) {
				const term = pendingCustomerSearch.value;
				pendingCustomerSearch.value = null;
				await searchCustomers(term);
			}
		}
	}

	async function verifyServerCustomerCount() {
		if (!posProfile.value || isOffline()) {
			return;
		}
		try {
			const localCount = await getCustomerStorageCount();
			const serializedProfile = getSerializedProfile(posProfile.value);
			if (!serializedProfile) {
				return;
			}
			const response = await (frappe.call as any)({
				method: "posawesome.posawesome.api.customers.get_customers_count",
				args: { pos_profile: serializedProfile },
			});
			const serverCount = response.message || 0;
			logServerCustomerCount(serverCount);
			totalCustomerCount.value = serverCount;
			loadedCustomerCount.value = localCount;
			syncBootstrapCustomerReadiness(localCount);
			loadProgress.value = serverCount
				? Math.round((localCount / serverCount) * 100)
				: 0;

			if (serverCount > localCount) {
				const syncSince = getCustomersLastSync();
				const rows: Customer[] = await fetchCustomerPage(
					null,
					syncSince,
					PAGE_SIZE,
				);
				if (rows.length) {
					await setCustomerStorage(rows);
				}
				const startAfter =
					rows.length === PAGE_SIZE
						? rows[rows.length - 1]?.name || null
						: null;
				if (startAfter) {
					await backgroundLoadCustomers(startAfter);
				}

				// If the cache is still short after the delta pass, the missing
				// rows are older than the watermark and no delta can ever reach
				// them. Rebuild from scratch instead of looping on this forever.
				const afterDelta = await getCustomerStorageCount();
				if (afterDelta < serverCount) {
					console.warn(
						`Customer cache short by ${serverCount - afterDelta} after delta sync; running full resync`,
					);
					await fullResyncCustomers(serverCount);
				} else {
					await finalizeCustomerSync();
				}
				await searchCustomers(searchTerm.value);
			} else if (serverCount < localCount) {
				await fullResyncCustomers(serverCount);
				await searchCustomers(searchTerm.value);
			} else {
				if (customersLoaded.value || localCount > 0) {
					logFinalLoadedCustomerCount();
				}
			}
		} catch (err) {
			console.error("Error verifying customer count:", err);
		}
	}

	async function load_customer_names_internal() {
		if (!posProfile.value) {
			console.debug("Customer fetch skipped: POS Profile not ready");
			return;
		}
		await ensureCustomerScopeIsolation();
		const serializedProfile = getSerializedProfile(posProfile.value);
		if (!serializedProfile) {
			return;
		}

		await ensureDatabase();
		const localCount = await getCustomerStorageCount();
		logLocalCustomerCount(localCount);
		syncBootstrapCustomerReadiness(localCount);

		if (localCount > 0) {
			customersLoaded.value = true;
			await searchCustomers(searchTerm.value);
			await verifyServerCustomerCount();
			if (!nextCustomerStart.value) {
				logFinalLoadedCustomerCount();
			}
			return;
		}

		// The cache is empty here, so this is a from-scratch load. A watermark
		// that outlived the cache would filter this fetch down to "changed
		// since then" - usually nothing - and strand every existing customer.
		const syncSince = null;
		if (getCustomersLastSync()) {
			setCustomersLastSync(null);
		}

		loadProgress.value = 0;
		loadingCustomers.value = true;
		try {
			try {
				const countResponse = await (frappe.call as any)({
					method: "posawesome.posawesome.api.customers.get_customers_count",
					args: { pos_profile: serializedProfile },
				});
				totalCustomerCount.value = countResponse.message || 0;
				logServerCustomerCount(totalCustomerCount.value);
			} catch (err) {
				console.error("Failed to fetch customer count", err);
				totalCustomerCount.value = 0;
			}

			const rows: Customer[] = await fetchCustomerPage(
				null,
				syncSince,
				PAGE_SIZE,
			);

			if (rows.length) {
				await setCustomerStorage(rows);
			}
			loadedCustomerCount.value = rows.length;
			syncBootstrapCustomerReadiness(loadedCustomerCount.value);
			if (totalCustomerCount.value) {
				loadProgress.value = Math.min(
					100,
					Math.round(
						(loadedCustomerCount.value / totalCustomerCount.value) *
							100,
					),
				);
			}
			nextCustomerStart.value =
				rows.length === PAGE_SIZE
					? rows[rows.length - 1]?.name || null
					: null;
			if (nextCustomerStart.value) {
				void backgroundLoadCustomers(nextCustomerStart.value);
			} else {
				await finalizeCustomerSync();
			}
			customersLoaded.value = true;
		} catch (err) {
			console.error("Failed to fetch customers:", err);
		} finally {
			loadingCustomers.value = false;
			customersLoaded.value = true;
			await searchCustomers(searchTerm.value);
		}
	}

	async function get_customer_names() {
		if (customerFetchPromise) {
			return customerFetchPromise;
		}

		resetCustomerLoadLogState();
		customerFetchPromise = load_customer_names_internal().finally(() => {
			customerFetchPromise = null;
		});
		return customerFetchPromise;
	}

	async function addOrUpdateCustomer(customer: Customer) {
		if (!customer || !customer.name || !isCustomerVisible(customer)) {
			return;
		}
		const existingIndex = customers.value.findIndex(
			(c) => c.name === customer.name,
		);
		if (existingIndex !== -1) {
			const updated = [...customers.value];
			updated.splice(existingIndex, 1, customer);
			customers.value = updated;
		} else {
			customers.value = [...customers.value, customer];
		}
		await setCustomerStorage([customer]);
		syncBootstrapCustomerReadiness(Math.max(customers.value.length, 1));
		setSelectedCustomer(customer.name);
		requestCustomerRefresh();
	}

	async function reloadCustomers() {
		if (isOffline()) {
			console.warn("Cannot reload customers while offline");
			return;
		}

		clearLocalState();
		await clearCustomerStorage();
		setCustomersLastSync(null);
		syncBootstrapCustomerReadiness(0);

		await get_customer_names();

		if (posProfile.value && posProfile.value.customer) {
			setSelectedCustomer(posProfile.value.customer);
		}
	}

	function openUpdateCustomerDialog(customer: Customer | null = null) {
		customerToUpdate.value = customer;
		isUpdateCustomerDialogOpen.value = true;
	}

	function closeUpdateCustomerDialog() {
		isUpdateCustomerDialogOpen.value = false;
		customerToUpdate.value = null;
	}

	function clearLocalState() {
		resetPagination();
		selectedCustomer.value = null;
		customerInfo.value = {};
		loadProgress.value = 0;
		totalCustomerCount.value = 0;
		loadedCustomerCount.value = 0;
		customersLoaded.value = false;
		nextCustomerStart.value = null;
		resetCustomerLoadLogState();
	}

	return {
		customers,
		filteredCustomers,
		selectedCustomer,
		customerInfo,
		searchTerm,
		page,
		hasMore,
		nextCustomerStart,
		loadingCustomers,
		customersLoaded,
		isCustomerBackgroundLoading,
		pendingCustomerSearch,
		loadProgress,
		totalCustomerCount,
		loadedCustomerCount,
		posProfile,
		refreshToken,
		isLoadComplete,
		setPosProfile,
		setSelectedCustomer,
		setCustomerInfo,
		searchCustomers,
		queueSearch,
		loadMoreCustomers,
		verifyServerCustomerCount,
		fullResyncCustomers,
		get_customer_names,
		backgroundLoadCustomers,
		addOrUpdateCustomer,
		requestCustomerRefresh,
		reloadCustomers,
		clearLocalState,
		isUpdateCustomerDialogOpen,
		customerToUpdate,
		openUpdateCustomerDialog,
		closeUpdateCustomerDialog,
	};
});
