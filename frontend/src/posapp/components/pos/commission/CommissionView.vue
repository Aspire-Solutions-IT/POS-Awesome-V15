<template>
	<v-card class="commission-view pos-themed-card">
		<div class="commission-view__header">
			<div>
				<p class="commission-view__eyebrow">{{ __("Sales Partner") }}</p>
				<h2 class="commission-view__title">{{ __("My Commission") }}</h2>
				<p class="commission-view__subtitle">
					{{ __("Commission on your submitted orders. Tick Delivered only to see what has already been delivered.") }}
				</p>
			</div>
			<v-btn icon="mdi-refresh" variant="text" :loading="loading" :aria-label="__('Refresh')" @click="load" />
		</div>

		<div class="commission-view__summary">
			<div>
				<span>{{ __("Commission owed") }}</span>
				<strong>{{ money(totals.commission) }}</strong>
			</div>
			<div>
				<span>{{ __("Net value") }}</span>
				<strong>{{ money(totals.net_value) }}</strong>
			</div>
			<div>
				<span>{{ __("Orders") }}</span>
				<strong>{{ totals.orders }}</strong>
			</div>
		</div>

		<div class="commission-view__filters">
			<v-checkbox
				v-model="deliveredOnly"
				:label="__('Delivered only')"
				density="compact"
				hide-details
				@update:model-value="reload"
			/>
			<v-text-field
				v-model="fromDate"
				type="date"
				:label="__('From')"
				density="compact"
				hide-details
				class="pos-themed-input"
				@update:model-value="reload"
			/>
			<v-text-field
				v-model="toDate"
				type="date"
				:label="__('To')"
				density="compact"
				hide-details
				class="pos-themed-input"
				@update:model-value="reload"
			/>
		</div>

		<v-alert v-if="error" type="error" variant="tonal" density="compact" class="mb-3">{{ error }}</v-alert>

		<v-table class="commission-view__table" density="comfortable">
			<thead>
				<tr>
					<th>{{ __("Date") }}</th>
					<th>{{ __("Order") }}</th>
					<th>{{ __("Customer") }}</th>
					<th class="text-end">{{ __("Net value") }}</th>
					<th class="text-end">{{ __("Rate") }}</th>
					<th class="text-end">{{ __("Commission") }}</th>
					<th>{{ __("Status") }}</th>
				</tr>
			</thead>
			<tbody>
				<tr v-if="!loading && !rows.length">
					<td colspan="7" class="text-center text-medium-emphasis">{{ __("No orders found.") }}</td>
				</tr>
				<tr v-for="row in rows" :key="row.name">
					<td>{{ formatDate(row.transaction_date) }}</td>
					<td>{{ row.name }}</td>
					<td>{{ row.customer_name || row.customer }}</td>
					<td class="text-end">{{ money(row.net_value) }}</td>
					<td class="text-end">{{ Number(row.commission_rate || 0) }}%</td>
					<td class="text-end">{{ money(row.commission) }}</td>
					<td>
						<v-chip size="small" :color="row.delivered ? 'success' : undefined" variant="tonal">
							{{ row.delivered ? __("Delivered") : row.status }}
						</v-chip>
					</td>
				</tr>
			</tbody>
		</v-table>

		<div class="commission-view__pager">
			<v-btn variant="text" :disabled="offset === 0 || loading" @click="page(-1)">{{ __("Previous") }}</v-btn>
			<span>{{ pageLabel }}</span>
			<v-btn variant="text" :disabled="offset + limit >= totals.orders || loading" @click="page(1)">
				{{ __("Next") }}
			</v-btn>
		</div>
	</v-card>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import api from "../../../services/api";
import { PARTNER_HOME_ROUTE, isPartnerMode } from "../../../utils/partnerMode";

declare const __: (_text: string, _args?: any[]) => string;
declare const frappe: any;

type Row = {
	name: string;
	transaction_date: string;
	customer: string;
	customer_name?: string;
	status: string;
	delivered: number;
	net_value: number;
	commission_rate: number;
	commission: number;
};
type Response = {
	rows: Row[];
	totals: { orders: number; net_value: number; commission: number };
	currency: string | null;
	limit: number;
	offset: number;
};

const router = useRouter();
const rows = ref<Row[]>([]);
const totals = ref({ orders: 0, net_value: 0, commission: 0 });
const currency = ref<string | null>(null);
const loading = ref(false);
const error = ref("");
const deliveredOnly = ref(false);
const fromDate = ref("");
const toDate = ref("");
const limit = ref(50);
const offset = ref(0);

const money = (value: number) => {
	const amount = Number(value || 0);
	try {
		return new Intl.NumberFormat(undefined, {
			style: "currency",
			currency: currency.value || "GBP",
		}).format(amount);
	} catch {
		return amount.toFixed(2);
	}
};
const formatDate = (value: string) => frappe.datetime.str_to_user(value);

const pageLabel = computed(() => {
	if (!totals.value.orders) return "";
	const from = offset.value + 1;
	const to = Math.min(offset.value + limit.value, totals.value.orders);
	return __("{0} - {1} of {2}", [from, to, totals.value.orders]);
});

let requestId = 0;
const load = async () => {
	const current = ++requestId;
	loading.value = true;
	error.value = "";
	try {
		const data = await api.call<Response>("posawesome.posawesome.api.partner_commission.get_partner_commission", {
			delivered_only: deliveredOnly.value ? 1 : 0,
			from_date: fromDate.value || undefined,
			to_date: toDate.value || undefined,
			limit: limit.value,
			offset: offset.value,
		});
		if (current !== requestId) return;
		rows.value = data?.rows || [];
		totals.value = data?.totals || { orders: 0, net_value: 0, commission: 0 };
		currency.value = data?.currency || null;
	} catch (e) {
		if (current !== requestId) return;
		error.value = __("Could not load your commission.");
	} finally {
		if (current === requestId) loading.value = false;
	}
};

const reload = () => {
	offset.value = 0;
	void load();
};

const page = (direction: number) => {
	offset.value = Math.max(0, offset.value + direction * limit.value);
	void load();
};

onMounted(() => {
	// Only partners have commission to show; anyone else typing the address goes back to the POS.
	if (!isPartnerMode()) {
		void router.replace(PARTNER_HOME_ROUTE);
		return;
	}
	void load();
});
</script>

<style scoped>
.commission-view {
	padding: 20px;
}
.commission-view__header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	margin-bottom: 12px;
}
.commission-view__eyebrow {
	margin: 0;
	font-size: 0.75rem;
	text-transform: uppercase;
	letter-spacing: 0.06em;
	color: var(--pos-text-secondary);
}
.commission-view__title {
	margin: 2px 0;
}
.commission-view__subtitle {
	margin: 0;
	color: var(--pos-text-secondary);
}
.commission-view__summary {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
	gap: 12px;
	margin-bottom: 16px;
}
.commission-view__summary > div {
	display: flex;
	flex-direction: column;
	padding: 12px 16px;
	border-radius: 8px;
	background: var(--pos-surface-muted);
}
.commission-view__summary strong {
	font-size: 1.25rem;
}
.commission-view__filters {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 12px;
	margin-bottom: 12px;
}
.commission-view__filters .v-text-field {
	max-width: 180px;
}
.commission-view__pager {
	display: flex;
	align-items: center;
	justify-content: flex-end;
	gap: 8px;
	margin-top: 8px;
}
</style>
