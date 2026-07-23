<template>
	<v-container fluid class="sales-order-management">
		<v-row>
			<v-col cols="12">
				<div class="page-header">
					<div>
						<h1 class="page-title">{{ __("Sales Order Management") }}</h1>
						<p class="page-subtitle">
							{{ __("Browse RFS Sales Orders, review due dates, and update key order details.") }}
						</p>
					</div>
				</div>
			</v-col>
		</v-row>

		<v-row v-if="!profileReady">
			<v-col cols="12">
				<v-card class="pos-themed-card">
					<v-card-text class="text-medium-emphasis">
						{{ __("Loading POS profile...") }}
					</v-card-text>
				</v-card>
			</v-col>
		</v-row>

		<v-row v-else-if="!canAccess">
			<v-col cols="12">
				<v-alert type="warning" variant="tonal" border="start">
					{{ __("This page is only available when Select S.O is enabled for the current POS Profile.") }}
				</v-alert>
			</v-col>
		</v-row>

		<v-row v-else class="content-grid">
			<v-col cols="12" lg="4">
				<v-card class="pos-themed-card left-panel">
					<v-card-title class="panel-title">
						<span>{{ __("RFS Sales Orders") }}</span>
						<v-btn
							icon="mdi-refresh"
							variant="text"
							size="small"
							:loading="listLoading"
							@click="loadOrders"
						/>
					</v-card-title>
					<v-card-text>
						<div class="search-row">
							<v-text-field
								v-model="searchTerm"
								:label="__('Sales Order')"
								density="compact"
								hide-details
								clearable
								class="pos-themed-input"
								@keyup.enter="loadOrders"
							/>
							<v-btn color="primary" :loading="listLoading" @click="loadOrders">
								{{ __("Search") }}
							</v-btn>
						</div>
						<v-alert
							v-if="listError"
							type="error"
							variant="tonal"
							density="compact"
							border="start"
							class="mt-4"
						>
							{{ listError }}
						</v-alert>
						<div v-if="listLoading" class="panel-placeholder">
							{{ __("Loading sales orders...") }}
						</div>
						<div v-else-if="!orders.length" class="panel-placeholder">
							{{ __("No Sales Orders found.") }}
						</div>
						<div v-else class="order-list">
							<button
								v-for="order in orders"
								:key="order.name"
								type="button"
								class="order-list-item"
								:class="{ 'order-list-item--active': order.name === selectedOrderName }"
								@click="selectOrder(order.name)"
							>
								<div class="order-list-item__top">
									<strong>{{ order.name }}</strong>
									<span>{{ order.status || __("Unknown") }}</span>
								</div>
								<div class="order-list-item__meta">
									<span>{{ order.customer_name || order.customer }}</span>
									<span>{{ formatDate(order.transaction_date) }}</span>
								</div>
								<div class="order-list-item__meta">
									<span>{{ __("Preferred") }}: {{ formatDate(order.prefered_earliest_delivery_date) }}</span>
									<span>{{ formatCurrency(order.rounded_total || order.grand_total, order.currency) }}</span>
								</div>
							</button>
						</div>
					</v-card-text>
				</v-card>
			</v-col>

			<v-col cols="12" lg="8">
				<v-card class="pos-themed-card right-panel">
					<v-card-title class="panel-title">
						<span>{{ selectedOrder?.name || __("Sales Order Details") }}</span>
						<div class="panel-actions">
							<v-btn
								v-if="canPayRemainingBalance"
								color="success"
								variant="flat"
								:loading="paymentLoading"
								:disabled="paymentLoading"
								@click="openPaymentDialog"
							>
								{{ __("Pay Remaining Balance") }}
							</v-btn>
							<v-btn
								color="primary"
								:loading="saveLoading"
								:disabled="!selectedOrder || !isDirty"
								@click="saveOrder"
							>
								{{ __("Save") }}
							</v-btn>
						</div>
					</v-card-title>
					<v-card-text>
						<v-alert
							v-if="detailError"
							type="error"
							variant="tonal"
							density="compact"
							border="start"
							class="mb-4"
						>
							{{ detailError }}
						</v-alert>
						<div v-if="detailLoading" class="panel-placeholder">
							{{ __("Loading order details...") }}
						</div>
						<div v-else-if="!selectedOrder" class="panel-placeholder">
							{{ __("Choose a Sales Order to review and update it.") }}
						</div>
						<div v-else class="detail-grid">
							<div class="detail-summary">
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Customer") }}</span>
									<strong>{{ selectedOrder.customer_name || selectedOrder.customer }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Status") }}</span>
									<strong>{{ selectedOrder.status || __("Unknown") }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Latest Component Due") }}</span>
									<strong>{{ formatDate(selectedOrder.latest_component_due_date) }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Auto Release") }}</span>
									<strong>{{ formatDate(selectedOrder.auto_release_date) }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Paid") }}</span>
									<strong>{{ formatCurrency(selectedOrder.advance_paid, selectedOrder.currency) }}</strong>
								</div>
								<div class="summary-chip">
									<span class="summary-chip__label">{{ __("Outstanding") }}</span>
									<strong>{{ formatCurrency(selectedOrder.outstanding_balance, selectedOrder.currency) }}</strong>
								</div>
							</div>

							<v-row dense>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="selectedOrder.name"
										:label="__('Sales Order')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="selectedOrder.customer_order_ref || ''"
										:label="__('Payment Ref')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										v-model="form.customer_ref"
										:label="__('Customer Ref')"
										density="compact"
										hide-details
										class="pos-themed-input"
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="formatDate(selectedOrder.transaction_date)"
										:label="__('Transaction Date')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12" md="6">
									<VueDatePicker
										:model-value="form.prefered_earliest_delivery_date || null"
										model-type="yyyy-MM-dd"
										format="dd-MM-yyyy"
										:enable-time-picker="false"
										auto-apply
										class="sleek-field pos-themed-input"
										:placeholder="__('Preferred Delivery Date')"
										@update:model-value="
											form.prefered_earliest_delivery_date = ($event as string | null) || ''
										"
									/>
								</v-col>
								<v-col cols="12" md="6">
									<v-text-field
										:model-value="selectedOrder.shipping_address_name || ''"
										:label="__('Shipping Address')"
										density="compact"
										readonly
										hide-details
									/>
								</v-col>
								<v-col cols="12">
									<v-textarea
										v-model="form.posa_notes"
										:label="__('Notes')"
										rows="4"
										auto-grow
										hide-details
										class="pos-themed-input"
									/>
								</v-col>
							</v-row>

							<div class="items-section">
								<div class="items-section__header">
									<h3>{{ __("Items") }}</h3>
									<span>{{ __("Component due dates are shown per line.") }}</span>
								</div>
								<div class="items-table-wrapper">
									<v-table density="compact">
										<thead>
											<tr>
												<th>{{ __("Item") }}</th>
												<th>{{ __("Qty") }}</th>
												<th>{{ __("Delivered") }}</th>
												<th>{{ __("Warehouse") }}</th>
												<th>{{ __("Delivery Date") }}</th>
												<th>{{ __("Component Due Date") }}</th>
											</tr>
										</thead>
										<tbody>
											<tr v-for="item in selectedOrder.items || []" :key="item.name">
												<td>
													<div class="item-cell">
														<strong>{{ item.item_code }}</strong>
														<span>{{ item.item_name }}</span>
													</div>
												</td>
												<td>{{ item.qty }}</td>
												<td>{{ item.delivered_qty }}</td>
												<td>{{ item.warehouse || __("N/A") }}</td>
												<td>{{ formatDate(item.delivery_date) }}</td>
												<td>{{ formatDate(item.component_due_date) }}</td>
											</tr>
										</tbody>
									</v-table>
								</div>
							</div>
						</div>
					</v-card-text>
				</v-card>
			</v-col>
		</v-row>

		<v-dialog v-model="paymentDialogOpen" max-width="460">
			<v-card class="pos-themed-card">
				<v-card-title>{{ __("Pay Remaining Balance") }}</v-card-title>
				<v-card-text class="pt-2">
					<v-alert
						v-if="paymentError"
						type="error"
						variant="tonal"
						density="compact"
						border="start"
						class="mb-4"
					>
						{{ paymentError }}
					</v-alert>
					<div class="payment-balance-copy mb-4">
						<span class="payment-balance-copy__label">{{ __("Remaining Balance") }}</span>
						<strong class="payment-balance-copy__amount">
							{{ formatCurrency(selectedOrder?.outstanding_balance, selectedOrder?.currency) }}
						</strong>
					</div>
					<v-text-field
						v-model="paymentForm.amount"
						:label="__('Payment Amount')"
						density="compact"
						hide-details
						type="number"
						step="0.01"
						min="0"
						class="pos-themed-input mb-4"
					/>
					<v-select
						v-model="paymentForm.mode_of_payment"
						:items="paymentModeOptions"
						item-title="label"
						item-value="value"
						:label="__('Mode of Payment')"
						density="compact"
						hide-details
						class="pos-themed-input mb-4"
					/>
					<v-text-field
						v-model="paymentForm.reference_no"
						:label="__('Reference No')"
						density="compact"
						readonly
						hide-details
						class="pos-themed-input"
					/>
				</v-card-text>
				<v-card-actions class="justify-end">
					<v-btn variant="text" @click="closePaymentDialog">
						{{ __("Cancel") }}
					</v-btn>
					<v-btn
						color="success"
						variant="flat"
						:loading="paymentLoading"
						:disabled="paymentLoading || !paymentForm.mode_of_payment"
						@click="submitRemainingBalancePayment"
					>
						{{ __("Pay Now") }}
					</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	</v-container>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import api from "../../../services/api";
import { useToastStore } from "../../../stores/toastStore.js";
import { useUIStore } from "../../../stores/uiStore.js";
import { storeToRefs } from "pinia";

declare const __: (value: string, args?: any[]) => string;

type ManagedSalesOrderListRow = {
	name: string;
	customer?: string;
	customer_name?: string;
	status?: string;
	transaction_date?: string | null;
	prefered_earliest_delivery_date?: string | null;
	customer_ref?: string | null;
	customer_order_ref?: string | null;
	currency?: string | null;
	grand_total?: number | null;
	rounded_total?: number | null;
	advance_paid?: number | null;
	outstanding_balance?: number | null;
	modified?: string | null;
};

type ManagedSalesOrderDetail = ManagedSalesOrderListRow & {
	auto_release_date?: string | null;
	shipping_address_name?: string | null;
	customer_address?: string | null;
	posa_notes?: string | null;
	shopify_notes?: string | null;
	latest_component_due_date?: string | null;
	advance_paid?: number | null;
	outstanding_balance?: number | null;
	items?: Array<{
		name: string;
		item_code: string;
		item_name?: string | null;
		warehouse?: string | null;
		qty?: number | null;
		delivered_qty?: number | null;
		delivery_date?: string | null;
		component_due_date?: string | null;
	}>;
};

const uiStore = useUIStore();
const toastStore = useToastStore();
const { posProfile } = storeToRefs(uiStore);

const profileReady = computed(() => Boolean(posProfile.value?.name));
const canAccess = computed(() => Number(posProfile.value?.custom_allow_select_sales_order || 0) === 1);

const orders = ref<ManagedSalesOrderListRow[]>([]);
const selectedOrder = ref<ManagedSalesOrderDetail | null>(null);
const selectedOrderName = ref("");
const searchTerm = ref("");
const listLoading = ref(false);
const detailLoading = ref(false);
const saveLoading = ref(false);
const paymentLoading = ref(false);
const listError = ref("");
const detailError = ref("");
const paymentDialogOpen = ref(false);
const paymentError = ref("");

const paymentForm = reactive({
	amount: "",
	mode_of_payment: "",
	reference_no: "",
});

const form = reactive({
	customer_ref: "",
	prefered_earliest_delivery_date: "",
	posa_notes: "",
});

const resetForm = (order: ManagedSalesOrderDetail | null) => {
	form.customer_ref = String(order?.customer_ref || "");
	form.prefered_earliest_delivery_date = String(order?.prefered_earliest_delivery_date || "");
	form.posa_notes = String(order?.posa_notes || "");
};

const isDirty = computed(() => {
	if (!selectedOrder.value) return false;
	return (
		form.customer_ref !== String(selectedOrder.value.customer_ref || "") ||
		form.prefered_earliest_delivery_date !==
			String(selectedOrder.value.prefered_earliest_delivery_date || "") ||
		form.posa_notes !== String(selectedOrder.value.posa_notes || "")
	);
});

const paymentModeOptions = computed(() =>
	(Array.isArray(posProfile.value?.payments) ? posProfile.value.payments : [])
		.map((row: any) => {
			const mode = String(row?.mode_of_payment || "").trim();
			if (!mode) return null;
			return {
				label: mode,
				value: mode,
			};
		})
		.filter(Boolean) as Array<{ label: string; value: string }>,
);

const canPayRemainingBalance = computed(
	() => Number(selectedOrder.value?.outstanding_balance || 0) > 0.001 && paymentModeOptions.value.length > 0,
);

const formatDate = (value?: string | null) => {
	if (!value) return __("N/A");
	const parsed = new Date(`${value}T00:00:00`);
	if (Number.isNaN(parsed.getTime())) {
		return value;
	}
	return new Intl.DateTimeFormat("en-GB", {
		day: "2-digit",
		month: "2-digit",
		year: "numeric",
	}).format(parsed);
};

const formatCurrency = (value?: number | null, currency?: string | null) => {
	const amount = Number(value || 0);
	try {
		return new Intl.NumberFormat(undefined, {
			style: "currency",
			currency: currency || posProfile.value?.currency || "GBP",
			maximumFractionDigits: 2,
		}).format(amount);
	} catch {
		return amount.toFixed(2);
	}
};

const syncSelectedListRow = (detail: ManagedSalesOrderDetail) => {
	const index = orders.value.findIndex((entry) => entry.name === detail.name);
	if (index === -1) return;
	const existing = orders.value[index];
	if (!existing) return;
	orders.value.splice(index, 1, {
		...existing,
		customer_ref: detail.customer_ref,
		prefered_earliest_delivery_date: detail.prefered_earliest_delivery_date,
		advance_paid: detail.advance_paid,
		outstanding_balance: detail.outstanding_balance,
		modified: detail.modified,
	});
};

const closePaymentDialog = () => {
	paymentDialogOpen.value = false;
	paymentError.value = "";
	paymentForm.amount = "";
	paymentForm.mode_of_payment = "";
	paymentForm.reference_no = "";
};

const openPaymentDialog = () => {
	if (!selectedOrder.value) return;
	paymentError.value = "";
	paymentForm.amount = String(selectedOrder.value.outstanding_balance || "");
	paymentForm.mode_of_payment = paymentModeOptions.value[0]?.value || "";
	paymentForm.reference_no = selectedOrder.value.customer_order_ref || selectedOrder.value.name || "";
	paymentDialogOpen.value = true;
};

const loadOrders = async () => {
	if (!canAccess.value || !posProfile.value?.company || !posProfile.value?.currency) {
		return;
	}

	listLoading.value = true;
	listError.value = "";

	try {
		const message = await api.call<ManagedSalesOrderListRow[]>(
			"posawesome.posawesome.api.sales_orders.get_managed_sales_orders",
			{
				company: posProfile.value.company,
				currency: posProfile.value.currency,
				order_name: searchTerm.value || null,
			},
		);
		orders.value = Array.isArray(message) ? message : [];

		if (selectedOrderName.value) {
			const stillExists = orders.value.some((entry) => entry.name === selectedOrderName.value);
			if (stillExists) {
				await selectOrder(selectedOrderName.value);
				return;
			}
		}

		if (orders.value.length) {
			const firstOrder = orders.value[0];
			if (firstOrder?.name) {
				await selectOrder(firstOrder.name);
			}
		} else {
			selectedOrder.value = null;
			selectedOrderName.value = "";
			resetForm(null);
		}
	} catch (error) {
		console.error("Failed to load managed sales orders", error);
		listError.value = __("Unable to fetch Sales Orders");
	} finally {
		listLoading.value = false;
	}
};

const selectOrder = async (name: string) => {
	if (!name || detailLoading.value) return;

	selectedOrderName.value = name;
	detailLoading.value = true;
	detailError.value = "";

	try {
		const message = await api.call<ManagedSalesOrderDetail>(
			"posawesome.posawesome.api.sales_orders.get_managed_sales_order",
			{
				sales_order: name,
			},
		);
		selectedOrder.value = message || null;
		resetForm(selectedOrder.value);
	} catch (error) {
		console.error("Failed to load Sales Order detail", error);
		detailError.value = __("Unable to load the selected Sales Order");
	} finally {
		detailLoading.value = false;
	}
};

const saveOrder = async () => {
	if (!selectedOrder.value || saveLoading.value || !isDirty.value) return;

	saveLoading.value = true;
	detailError.value = "";

	try {
		const message = await api.call<ManagedSalesOrderDetail>(
			"posawesome.posawesome.api.sales_orders.update_managed_sales_order",
			{
				data: {
					name: selectedOrder.value.name,
					customer_ref: form.customer_ref,
					prefered_earliest_delivery_date: form.prefered_earliest_delivery_date || null,
					posa_notes: form.posa_notes,
				},
			},
		);
		selectedOrder.value = message || null;
		resetForm(selectedOrder.value);
		if (selectedOrder.value) {
			syncSelectedListRow(selectedOrder.value);
		}
		toastStore.show({
			title: __("Sales Order updated"),
			color: "success",
		});
	} catch (error) {
		console.error("Failed to update managed Sales Order", error);
		detailError.value = __("Unable to update the Sales Order");
	} finally {
		saveLoading.value = false;
	}
};

const submitRemainingBalancePayment = async () => {
	if (!selectedOrder.value || !paymentForm.mode_of_payment) return;

	paymentLoading.value = true;
	paymentError.value = "";

	try {
		const message = await api.call<{
			sales_order: ManagedSalesOrderDetail;
			payment_entry: string;
		}>(
			"posawesome.posawesome.api.sales_orders.pay_managed_sales_order_balance",
			{
				sales_order: selectedOrder.value.name,
				mode_of_payment: paymentForm.mode_of_payment,
				amount: paymentForm.amount,
				reference_no: paymentForm.reference_no || null,
			},
			{
				freeze: true,
				freeze_message: __("Creating payment..."),
			},
		);

		selectedOrder.value = message?.sales_order || selectedOrder.value;
		if (selectedOrder.value) {
			syncSelectedListRow(selectedOrder.value);
		}
		toastStore.show({
								title: __("Payment Entry {0} created", [message?.payment_entry || ""]),
			color: "success",
		});
		closePaymentDialog();
	} catch (error: any) {
		console.error("Failed to pay managed Sales Order balance", error);
		paymentError.value =
			error?.message?.message ||
			error?.message ||
			__("Unable to create the remaining balance payment");
	} finally {
		paymentLoading.value = false;
	}
};

watch(
	() => [profileReady.value, canAccess.value, posProfile.value?.company, posProfile.value?.currency],
	([ready, access]) => {
		if (ready && access) {
			void loadOrders();
		}
	},
	{ immediate: true },
);
</script>

<style scoped>
.sales-order-management {
	padding: 20px;
}

.page-header {
	display: flex;
	justify-content: space-between;
	align-items: flex-start;
	gap: 16px;
}

.page-title {
	margin: 0;
	font-size: 1.7rem;
	font-weight: 700;
	color: var(--pos-text-primary);
}

.page-subtitle {
	margin: 6px 0 0;
	color: var(--pos-text-muted);
	max-width: 720px;
}

.content-grid {
	align-items: stretch;
}

.left-panel,
.right-panel {
	height: 100%;
}

.panel-title {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	border-bottom: 1px solid var(--pos-border);
}

.panel-actions {
	display: flex;
	align-items: center;
	gap: 10px;
	flex-wrap: wrap;
}

.payment-balance-copy {
	display: flex;
	flex-direction: column;
	gap: 4px;
	padding: 12px 14px;
	border: 1px solid var(--pos-border);
	border-radius: 14px;
	background: var(--pos-surface);
}

.payment-balance-copy__label {
	font-size: 0.85rem;
	color: var(--pos-text-muted);
}

.payment-balance-copy__amount {
	font-size: 1.05rem;
	color: var(--pos-text-primary);
}

.search-row {
	display: grid;
	grid-template-columns: minmax(0, 1fr) auto;
	gap: 12px;
	align-items: end;
}

.panel-placeholder {
	padding: 28px 8px;
	color: var(--pos-text-muted);
	text-align: center;
}

.order-list {
	display: grid;
	gap: 12px;
	margin-top: 16px;
}

.order-list-item {
	border: 1px solid var(--pos-border);
	border-radius: 16px;
	background: var(--pos-surface);
	color: var(--pos-text-primary);
	padding: 14px;
	text-align: left;
	transition:
		border-color 0.18s ease,
		transform 0.18s ease,
		box-shadow 0.18s ease;
}

.order-list-item:hover {
	transform: translateY(-1px);
	border-color: var(--pos-primary);
	box-shadow: 0 8px 18px var(--pos-shadow);
}

.order-list-item--active {
	border-color: var(--pos-primary);
	background: color-mix(in srgb, var(--pos-primary) 8%, var(--pos-surface));
}

.order-list-item__top,
.order-list-item__meta {
	display: flex;
	justify-content: space-between;
	gap: 12px;
}

.order-list-item__top {
	margin-bottom: 6px;
}

.order-list-item__meta {
	color: var(--pos-text-muted);
	font-size: 0.88rem;
}

.detail-grid {
	display: grid;
	gap: 18px;
}

.detail-summary {
	display: grid;
	grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
	gap: 12px;
}

.summary-chip {
	border: 1px solid var(--pos-border);
	border-radius: 16px;
	padding: 12px 14px;
	background: var(--pos-surface);
}

.summary-chip__label {
	display: block;
	font-size: 0.82rem;
	color: var(--pos-text-muted);
	margin-bottom: 6px;
}

.items-section {
	display: grid;
	gap: 12px;
}

.items-section__header {
	display: flex;
	justify-content: space-between;
	align-items: baseline;
	gap: 12px;
}

.items-section__header h3 {
	margin: 0;
	font-size: 1rem;
	color: var(--pos-text-primary);
}

.items-section__header span {
	color: var(--pos-text-muted);
	font-size: 0.85rem;
}

.items-table-wrapper {
	border: 1px solid var(--pos-border);
	border-radius: 18px;
	overflow: hidden;
	background: var(--pos-surface);
}

.item-cell {
	display: grid;
	gap: 4px;
}

.item-cell span {
	color: var(--pos-text-muted);
	font-size: 0.85rem;
}

@media (max-width: 960px) {
	.search-row {
		grid-template-columns: 1fr;
	}

	.items-section__header {
		flex-direction: column;
		align-items: flex-start;
	}
}
</style>
