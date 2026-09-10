<template>
	<v-card class="claims-view pos-themed-card">
		<div class="claims-view__header">
			<div>
				<p class="claims-view__eyebrow">{{ __("Customer Care") }}</p>
				<h2 class="claims-view__title">{{ __("Customer Claims") }}</h2>
				<p class="claims-view__subtitle">
					{{ __("Track reported issues and their resolution. Raise a new claim from Sales Order Management.") }}
				</p>
			</div>
			<v-btn
				icon="mdi-refresh"
				variant="text"
				:loading="listLoading"
				:aria-label="__('Refresh')"
				@click="refresh"
			/>
		</div>

		<div class="claims-view__summary">
			<button type="button" :class="{ active: filters.approval === '' && filters.progress === 'Open' }" @click="applySummary('open')">
				<span>{{ __("Open claims") }}</span>
				<strong>{{ counts.open }}</strong>
			</button>
			<button type="button" :class="{ active: filters.approval === 'Pending Approval' }" @click="applySummary('pending')">
				<span>{{ __("Awaiting approval") }}</span>
				<strong>{{ counts.pending }}</strong>
			</button>
			<button type="button" :class="{ active: filters.approval === 'Approved' }" @click="applySummary('approved')">
				<span>{{ __("Approved") }}</span>
				<strong>{{ counts.approved }}</strong>
			</button>
		</div>

		<v-alert
			v-if="filters.sales_order"
			type="info"
			variant="tonal"
			density="compact"
			border="start"
			class="mb-4"
		>
			{{ __("Showing claims for Sales Order {0}.", [filters.sales_order]) }}
			<v-btn size="x-small" variant="text" @click="clearSalesOrder">{{ __("Show all claims") }}</v-btn>
		</v-alert>

		<div class="claims-view__filters">
			<v-text-field
				v-model="filters.search"
				:label="__('Search claim, customer, order or description')"
				density="compact"
				hide-details
				clearable
				class="pos-themed-input"
				@update:model-value="scheduleReload"
			/>
			<v-select
				v-model="filters.approval"
				:items="approvalItems"
				:label="__('Approval')"
				density="compact"
				hide-details
				class="pos-themed-input"
				@update:model-value="reload"
			/>
			<v-select
				v-model="filters.progress"
				:items="progressItems"
				:label="__('Progress')"
				density="compact"
				hide-details
				class="pos-themed-input"
				@update:model-value="reload"
			/>
			<v-select
				v-model="filters.claim_type"
				:items="claimTypeItems"
				:label="__('Claim type')"
				density="compact"
				hide-details
				class="pos-themed-input"
				@update:model-value="reload"
			/>
			<v-text-field
				v-model="filters.assigned_to"
				:label="__('Owner email')"
				density="compact"
				hide-details
				clearable
				class="pos-themed-input"
				@update:model-value="scheduleReload"
			/>
		</div>

		<v-alert
			v-if="listError"
			type="error"
			variant="tonal"
			density="compact"
			border="start"
			class="mb-4"
		>
			{{ listError }}
			<v-btn size="x-small" variant="text" @click="refresh">{{ __("Retry") }}</v-btn>
		</v-alert>

		<div class="claims-view__body">
			<section class="claims-view__list" :aria-busy="listLoading">
				<div class="claims-view__list-head">
					<span>{{ filters.approval || __("All claims") }}</span>
					<span class="text-medium-emphasis">
						{{ listLoading ? __("Loading…") : __("{0} shown", [claims.length]) }}
					</span>
				</div>

				<div v-if="!claims.length && !listLoading" class="claims-view__placeholder">
					{{ __("No claims match these filters.") }}
				</div>

				<button
					v-for="claim in claims"
					:key="claim.name"
					type="button"
					class="claims-view__row"
					:class="{ 'claims-view__row--active': claim.name === selectedName }"
					@click="selectClaim(claim.name)"
				>
					<div class="claims-view__row-top">
						<strong>{{ claim.name }}</strong>
						<span class="claims-view__badge" :class="badgeClass(claim.workflow_state)">
							{{ claim.workflow_state }}
						</span>
					</div>
					<div class="claims-view__row-customer">{{ claim.customer }}</div>
					<div class="text-medium-emphasis">{{ claim.sales_order }} · {{ claim.claim_type }}</div>
					<div class="claims-view__row-bottom">
						<span>{{ claim.progress }} · {{ claim.preferred_outcome }}</span>
						<span>{{ formatDate(claim.modified) }}</span>
					</div>
				</button>

				<div class="claims-view__pagination">
					<v-btn size="small" variant="text" :disabled="start === 0 || listLoading" @click="page(-1)">
						{{ __("Previous") }}
					</v-btn>
					<span>{{ __("Page {0}", [start / PAGE_SIZE + 1]) }}</span>
					<v-btn size="small" variant="text" :disabled="!hasMore || listLoading" @click="page(1)">
						{{ __("Next") }}
					</v-btn>
				</div>
			</section>

			<section class="claims-view__detail" :aria-busy="detailLoading">
				<div v-if="detailLoading" class="claims-view__placeholder">{{ __("Loading claim…") }}</div>

				<template v-else-if="detail">
					<div class="claims-view__detail-head">
						<div>
							<p class="claims-view__eyebrow">{{ detail.claim.sales_order }}</p>
							<h3>{{ detail.claim.name }}</h3>
						</div>
						<div class="claims-view__detail-links">
							<v-btn
								v-if="detail.claim.sales_order"
								size="small"
								variant="tonal"
								color="primary"
								prepend-icon="mdi-clipboard-text-search-outline"
								@click="viewSalesOrder(detail.claim.sales_order)"
							>
								{{ __("View Sales Order") }}
							</v-btn>
							<a :href="formLink(detail.claim.name)" target="_blank" rel="noopener noreferrer">
								{{ __("Open full form ↗") }}
							</a>
						</div>
					</div>

					<div class="claims-view__status">
						<span class="claims-view__badge" :class="badgeClass(detail.claim.workflow_state)">
							{{ detail.claim.workflow_state }}
						</span>
						<span class="text-medium-emphasis">{{ __("Progress: {0}", [detail.claim.progress]) }}</span>
					</div>

					<h3 class="mt-2">{{ detail.claim.customer }}</h3>
					<p class="claims-view__description">{{ detail.claim.description }}</p>

					<div class="claims-view__facts">
						<div><span>{{ __("Claim type") }}</span><strong>{{ detail.claim.claim_type }}</strong></div>
						<div>
							<span>{{ __("Preferred outcome") }}</span>
							<strong>
								{{ detail.claim.preferred_outcome }}
								<template v-if="detail.claim.service_call_type"> · {{ detail.claim.service_call_type }}</template>
							</strong>
						</div>
						<div><span>{{ __("Owner") }}</span><strong>{{ detail.claim.assigned_to }}</strong></div>
						<div><span>{{ __("Raised by") }}</span><strong>{{ detail.claim.owner }}</strong></div>
					</div>

					<p v-if="detail.claim.approved_by" class="text-medium-emphasis">
						{{ __("Approved by {0} · {1}", [detail.claim.approved_by, formatDate(detail.claim.approved_on)]) }}
					</p>
					<v-alert
						v-if="detail.claim.rejection_reason"
						type="warning"
						variant="tonal"
						density="compact"
						border="start"
						class="my-2"
					>
						{{ __("Rejection reason: {0}", [detail.claim.rejection_reason]) }}
					</v-alert>
					<v-alert
						v-if="detail.previous_claims && detail.previous_claims.length"
						type="info"
						variant="tonal"
						density="compact"
						border="start"
						class="my-2"
					>
						{{ __("Previous claims for these items:") }}
						<a
							v-for="prev in detail.previous_claims"
							:key="prev.name"
							:href="formLink(prev.name)"
							target="_blank"
							rel="noopener noreferrer"
							class="ml-1"
						>{{ prev.name }}</a>
					</v-alert>

					<div v-if="evidenceUrl" class="my-3">
						<a :href="evidenceUrl" target="_blank" rel="noopener noreferrer">{{ __("View attached evidence ↗") }}</a>
					</div>

					<h4 class="mt-4">{{ __("Affected items") }}</h4>
					<v-table density="compact" class="mt-1">
						<thead>
							<tr>
								<th>{{ __("Item") }}</th>
								<th>{{ __("Quantity") }}</th>
								<th>{{ __("Fault details") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="item in detail.claim.items" :key="item.name">
								<td>
									<div>{{ item.item_code }}</div>
									<small class="text-medium-emphasis">{{ item.item_name }}</small>
								</td>
								<td>{{ item.qty }} {{ item.uom }}</td>
								<td>{{ item.fault_details || "—" }}</td>
							</tr>
						</tbody>
					</v-table>

					<h4 class="mt-4">
						{{ __("Resolution actions") }}
						<span class="text-medium-emphasis">({{ (detail.actions || []).length }})</span>
					</h4>
					<p v-if="!(detail.actions || []).length" class="text-medium-emphasis">
						{{ __("No actions yet.") }}
					</p>
					<article
						v-for="action in detail.actions"
						:key="action.name"
						class="claims-view__action"
					>
						<div class="claims-view__row-top">
							<strong>
								{{ action.action_type }}
								<template v-if="action.service_call_type"> · {{ action.service_call_type }}</template>
							</strong>
							<span class="claims-view__badge" :class="badgeClass(action.workflow_state)">
								{{ action.workflow_state }}
							</span>
						</div>
						<p>{{ action.description }}</p>
						<p class="text-medium-emphasis">{{ __("Execution: {0}", [action.execution_status]) }}</p>
						<p v-if="action.amount">{{ action.currency }} {{ action.amount }}</p>
					</article>
				</template>

				<div v-else class="claims-view__placeholder">
					{{ __("Select a claim to see its detail.") }}
				</div>
			</section>
		</div>
	</v-card>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import api from "../../../services/api";

declare const __: (value: string, args?: any[]) => string;

type ClaimRow = {
	name: string;
	customer?: string;
	sales_order?: string;
	claim_type?: string;
	assigned_to?: string;
	workflow_state?: string;
	progress?: string;
	preferred_outcome?: string;
	modified?: string;
};

type OverviewResponse = {
	claims: ClaimRow[];
	has_more: boolean;
	counts: { open: number; pending: number; approved: number };
	claim_types: Array<{ name: string }>;
};

type ClaimDetail = {
	claim: Record<string, any> & { items?: Array<Record<string, any>> };
	actions: Array<Record<string, any>>;
	available_actions: string[];
	previous_claims: Array<{ name: string }>;
	can_add_action: boolean;
};

const PAGE_SIZE = 25;

const claims = ref<ClaimRow[]>([]);
const detail = ref<ClaimDetail | null>(null);
const selectedName = ref("");
const listLoading = ref(false);
const detailLoading = ref(false);
const listError = ref("");
const start = ref(0);
const hasMore = ref(false);
const counts = reactive({ open: 0, pending: 0, approved: 0 });
const claimTypes = ref<Array<{ name: string }>>([]);

const route = useRoute();
const router = useRouter();

const filters = reactive({
	search: "",
	approval: "",
	progress: "Open",
	claim_type: "",
	assigned_to: "",
	sales_order: typeof route.query.sales_order === "string" ? route.query.sales_order : "",
});
// Arriving pre-filtered to one order (from Sales Order Management) should show
// every claim on it, not just the open ones.
if (filters.sales_order) filters.progress = "";

let searchTimer: ReturnType<typeof setTimeout> | undefined;
let listToken = 0;
let detailToken = 0;
let disposed = false;

const approvalItems = computed(() => [
	{ title: __("All approvals"), value: "" },
	{ title: "Draft", value: "Draft" },
	{ title: "Pending Approval", value: "Pending Approval" },
	{ title: "Approved", value: "Approved" },
	{ title: "Rejected", value: "Rejected" },
]);

const progressItems = computed(() => [
	{ title: __("All progress"), value: "" },
	{ title: "Open", value: "Open" },
	{ title: "In Progress", value: "In Progress" },
	{ title: "Closed", value: "Closed" },
]);

const claimTypeItems = computed(() => [
	{ title: __("All types"), value: "" },
	...claimTypes.value.map((type) => ({ title: type.name, value: type.name })),
]);

const evidenceUrl = computed(() => {
	const url = String(detail.value?.claim?.evidence || "");
	return /^\/(?!\/)/.test(url) || /^https?:\/\//i.test(url) ? url : "";
});

function badgeClass(state?: string) {
	return (
		{
			Approved: "is-approved",
			Rejected: "is-rejected",
			"Pending Approval": "is-pending",
		}[state || ""] || "is-draft"
	);
}

function formLink(name: string) {
	return `/app/customer-claim/${encodeURIComponent(name)}`;
}

function formatDate(value?: string | null) {
	if (!value) return "";
	const parsed = new Date(String(value).replace(" ", "T"));
	if (Number.isNaN(parsed.getTime())) return String(value);
	return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "2-digit", year: "numeric" }).format(parsed);
}

async function reload() {
	const token = ++listToken;
	listLoading.value = true;
	listError.value = "";
	try {
		const data = await api.call<OverviewResponse>("posawesome.posawesome.api.claims.list_claims", {
			search: filters.search || "",
			approval: filters.approval || "",
			progress: filters.progress || "",
			claim_type: filters.claim_type || "",
			assigned_to: filters.assigned_to || "",
			sales_order: filters.sales_order || "",
			start: start.value,
		});
		if (disposed || token !== listToken) return;
		claims.value = data.claims || [];
		hasMore.value = Boolean(data.has_more);
		Object.assign(counts, data.counts || {});
		claimTypes.value = data.claim_types || [];
	} catch (error: any) {
		if (token === listToken) {
			listError.value =
				error?.message?.message || error?.message || __("Could not load claims. Please try again.");
		}
	} finally {
		if (token === listToken) listLoading.value = false;
	}
}

function reloadFromStart() {
	start.value = 0;
	void reload();
}

function clearSalesOrder() {
	filters.sales_order = "";
	filters.progress = "Open";
	if (route.query.sales_order) {
		void router.replace({ path: "/claims", query: {} });
	}
	reloadFromStart();
}

function viewSalesOrder(salesOrder: string) {
	void router.push({ path: "/sales-orders", query: { sales_order: salesOrder } });
}

function scheduleReload() {
	clearTimeout(searchTimer);
	searchTimer = setTimeout(reloadFromStart, 300);
}

function applySummary(kind: "open" | "pending" | "approved") {
	if (kind === "open") {
		filters.approval = "";
		filters.progress = "Open";
	} else if (kind === "pending") {
		filters.approval = "Pending Approval";
		filters.progress = "";
	} else {
		filters.approval = "Approved";
		filters.progress = "";
	}
	reloadFromStart();
}

function page(direction: number) {
	start.value = Math.max(0, start.value + direction * PAGE_SIZE);
	void reload();
}

async function selectClaim(name: string) {
	const token = ++detailToken;
	selectedName.value = name;
	detailLoading.value = true;
	detail.value = null;
	try {
		const data = await api.call<ClaimDetail>("posawesome.posawesome.api.claims.get_claim", {
			claim: name,
		});
		if (!disposed && token === detailToken) detail.value = data;
	} catch (error: any) {
		if (token === detailToken) {
			listError.value =
				error?.message?.message || error?.message || __("Could not load this claim.");
		}
	} finally {
		if (token === detailToken) detailLoading.value = false;
	}
}

function refresh() {
	void reload();
	if (selectedName.value) void selectClaim(selectedName.value);
}

onMounted(reload);
onBeforeUnmount(() => {
	disposed = true;
	clearTimeout(searchTimer);
	listToken++;
	detailToken++;
});

defineExpose({ reload, selectClaim });
</script>

<style scoped>
.claims-view {
	padding: 20px;
}
.claims-view__header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 12px;
	margin-bottom: 18px;
}
.claims-view__eyebrow {
	font-size: 10px;
	letter-spacing: 1.6px;
	font-weight: 700;
	text-transform: uppercase;
	opacity: 0.6;
	margin: 0 0 4px;
}
.claims-view__title {
	font-size: 22px;
	margin: 0 0 4px;
}
.claims-view__subtitle {
	margin: 0;
	opacity: 0.7;
	font-size: 13px;
}
.claims-view__summary {
	display: grid;
	grid-template-columns: repeat(3, 1fr);
	gap: 12px;
	margin-bottom: 16px;
}
.claims-view__summary button {
	border: 1px solid var(--pos-border-color, rgba(0, 0, 0, 0.12));
	border-radius: 10px;
	padding: 12px 14px;
	text-align: left;
	background: transparent;
	color: inherit;
}
.claims-view__summary button.active {
	border-color: rgb(var(--v-theme-primary));
	box-shadow: inset 0 0 0 1px rgb(var(--v-theme-primary));
}
.claims-view__summary strong {
	display: block;
	font-size: 22px;
	margin-top: 4px;
}
.claims-view__filters {
	display: grid;
	grid-template-columns: 2fr 1fr 1fr 1fr 1.4fr;
	gap: 10px;
	margin-bottom: 16px;
}
.claims-view__body {
	display: grid;
	grid-template-columns: minmax(260px, 0.85fr) minmax(0, 1.4fr);
	gap: 16px;
	align-items: start;
}
.claims-view__list,
.claims-view__detail {
	border: 1px solid var(--pos-border-color, rgba(0, 0, 0, 0.12));
	border-radius: 10px;
	overflow: hidden;
}
.claims-view__detail {
	padding: 16px;
}
.claims-view__list-head {
	display: flex;
	justify-content: space-between;
	padding: 12px 14px;
	border-bottom: 1px solid var(--pos-border-color, rgba(0, 0, 0, 0.12));
	font-size: 12px;
}
.claims-view__row {
	display: block;
	width: 100%;
	text-align: left;
	background: transparent;
	color: inherit;
	border: 0;
	border-bottom: 1px solid var(--pos-border-color, rgba(0, 0, 0, 0.12));
	padding: 12px 14px;
	cursor: pointer;
}
.claims-view__row--active {
	background: rgba(var(--v-theme-primary), 0.08);
	box-shadow: inset 3px 0 rgb(var(--v-theme-primary));
}
.claims-view__row-top {
	display: flex;
	justify-content: space-between;
	align-items: center;
	gap: 8px;
}
.claims-view__row-customer {
	font-weight: 600;
	margin: 6px 0 2px;
}
.claims-view__row-bottom {
	display: flex;
	justify-content: space-between;
	margin-top: 8px;
	font-size: 11px;
	opacity: 0.7;
}
.claims-view__badge {
	font-size: 10px;
	font-weight: 700;
	border-radius: 20px;
	padding: 3px 8px;
	white-space: nowrap;
}
.claims-view__badge.is-approved {
	background: #e5f4ed;
	color: #246246;
}
.claims-view__badge.is-pending {
	background: #fff0d5;
	color: #8c5c13;
}
.claims-view__badge.is-rejected {
	background: #fbe9e7;
	color: #9d3933;
}
.claims-view__badge.is-draft {
	background: #edf0f4;
	color: #586477;
}
.claims-view__pagination {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 10px 14px;
	font-size: 12px;
}
.claims-view__placeholder {
	padding: 36px 16px;
	text-align: center;
	opacity: 0.6;
}
.claims-view__detail-links {
	display: flex;
	align-items: center;
	gap: 12px;
	flex-wrap: wrap;
	justify-content: flex-end;
}
.claims-view__detail-head {
	display: flex;
	justify-content: space-between;
	align-items: flex-start;
	gap: 12px;
}
.claims-view__status {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-top: 10px;
}
.claims-view__description {
	white-space: pre-wrap;
	margin: 8px 0;
}
.claims-view__facts {
	display: grid;
	grid-template-columns: 1fr 1fr;
	gap: 12px;
	margin: 14px 0;
}
.claims-view__facts span {
	display: block;
	font-size: 11px;
	opacity: 0.6;
}
.claims-view__action {
	border: 1px solid var(--pos-border-color, rgba(0, 0, 0, 0.12));
	border-radius: 8px;
	padding: 12px;
	margin-top: 10px;
	font-size: 12px;
}
@media (max-width: 1100px) {
	.claims-view__filters {
		grid-template-columns: 1fr 1fr;
	}
	.claims-view__body {
		grid-template-columns: 1fr;
	}
}
</style>
