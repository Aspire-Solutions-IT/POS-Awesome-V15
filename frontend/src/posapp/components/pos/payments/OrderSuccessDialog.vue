<template>
	<v-dialog
		:model-value="isOpen"
		max-width="560"
		persistent
		transition="dialog-bottom-transition"
		:retain-focus="false"
	>
		<v-card class="pos-themed-card order-success">
			<v-card-text class="pa-6">
				<div class="order-success__header">
					<v-icon color="success" size="44">mdi-check-circle</v-icon>
					<h2 class="order-success__title">{{ __("Payment Successful") }}</h2>
				</div>

				<div v-for="order in orders" :key="order.name" class="order-success__order">
					<div class="order-success__number">{{ order.name }}</div>

					<div v-if="order.customerName || order.total" class="order-success__meta">
						<span v-if="order.customerName">{{ order.customerName }}</span>
						<span v-if="order.customerName && order.total" class="order-success__dot">•</span>
						<span v-if="order.total">{{ order.total }}</span>
					</div>

					<!-- The reason this screen exists: the operator reads this out rather than
					     going hunting for it after the customer has already asked. -->
					<div class="order-success__window">
						<div class="order-success__window-label">
							{{ __("Estimated Delivery") }}
						</div>
						<div v-if="order.state === 'loading'" class="order-success__window-pending">
							<v-progress-circular indeterminate size="18" width="2" color="primary" />
							<span>{{ __("Confirming delivery window…") }}</span>
						</div>
						<div v-else-if="order.state === 'resolved'" class="order-success__window-value">
							{{ order.window }}
						</div>
						<div v-else class="order-success__window-pending">
							{{ __("Delivery window will be confirmed on the receipt") }}
						</div>
					</div>

					<v-btn
						v-if="orders.length > 1"
						color="primary"
						variant="tonal"
						size="small"
						prepend-icon="mdi-printer"
						class="mt-3"
						@click="printReceipt(order.name)"
					>
						{{ __("Print Receipt") }}
					</v-btn>
				</div>
			</v-card-text>

			<v-card-actions class="justify-end pa-4 pt-0">
				<v-btn variant="text" @click="close">
					{{ __("Done") }}
				</v-btn>
				<v-btn
					v-if="orders.length === 1"
					color="primary"
					variant="flat"
					prepend-icon="mdi-printer"
					@click="printReceipt(orders[0].name)"
				>
					{{ __("Print Receipt") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import { useUIStore } from "../../../stores/uiStore.js";
import { useFormat } from "../../../format";
import { openReceiptPdf } from "../../../utils/receiptPdfUrl";

defineOptions({
	name: "OrderSuccessDialog",
});

const __ = window.__ || ((text) => text);

const uiStore = useUIStore();
const { formatCurrency, currencySymbol } = useFormat();

// The window is written by an after_commit hook and can be revised again by the
// background work that follows submit, so it is polled rather than read from the
// submit response. Backs off so a slow settle costs a few requests, not a stream.
const RETRY_DELAYS_MS = [500, 1000, 2000, 2000, 2000];

const summaries = reactive({});
const timers = ref([]);

const isOpen = computed(() => Boolean(uiStore.orderSuccess));
const profile = computed(() => uiStore.orderSuccess?.profile || null);

const orderNames = computed(() => uiStore.orderSuccess?.orders || []);

const orders = computed(() =>
	orderNames.value.map((name) => {
		const summary = summaries[name] || { state: "loading" };
		return {
			name,
			state: summary.state,
			window: summary.window || "",
			customerName: summary.customerName || "",
			total: summary.total || "",
		};
	}),
);

const clearTimers = () => {
	timers.value.forEach((id) => clearTimeout(id));
	timers.value = [];
};

const formatTotal = (summary) => {
	if (summary?.grand_total === undefined || summary?.grand_total === null) return "";
	const symbol = summary.currency ? currencySymbol(summary.currency) : "";
	return `${symbol}${formatCurrency(summary.grand_total)}`;
};

const fetchSummary = async (name, attempt = 0) => {
	let message;
	try {
		const response = await frappe.call({
			method: "posawesome.posawesome.api.sales_orders.get_pos_order_summary",
			args: { sales_order: name },
		});
		message = response?.message;
	} catch (error) {
		// A failed lookup must never look like a failed payment.
		console.error("Failed to load order summary", error);
		summaries[name] = { ...(summaries[name] || {}), state: "unavailable" };
		return;
	}

	if (!message) {
		summaries[name] = { ...(summaries[name] || {}), state: "unavailable" };
		return;
	}

	const resolved = Boolean(message.settled);

	summaries[name] = {
		state: resolved ? "resolved" : attempt >= RETRY_DELAYS_MS.length ? "unavailable" : "loading",
		window: message.quoted_estimated_delivery_window || "",
		customerName: message.customer_name || "",
		total: formatTotal(message),
	};

	if (!resolved && attempt < RETRY_DELAYS_MS.length) {
		const id = setTimeout(() => fetchSummary(name, attempt + 1), RETRY_DELAYS_MS[attempt]);
		timers.value.push(id);
	}
};

const printReceipt = (name) => {
	openReceiptPdf({ name, profile: profile.value, doctype: "Sales Order" });
};

const close = () => {
	clearTimers();
	uiStore.closeOrderSuccess();
};

watch(
	orderNames,
	(names) => {
		clearTimers();
		Object.keys(summaries).forEach((key) => delete summaries[key]);
		names.forEach((name) => {
			summaries[name] = { state: "loading" };
			fetchSummary(name);
		});
	},
	{ immediate: true },
);

onBeforeUnmount(clearTimers);
</script>

<style scoped>
.order-success__header {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-bottom: 20px;
}

.order-success__title {
	font-size: 1.5rem;
	font-weight: 600;
	margin: 0;
}

.order-success__order + .order-success__order {
	margin-top: 20px;
	padding-top: 20px;
	border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.order-success__number {
	font-size: 1.35rem;
	font-weight: 600;
	letter-spacing: 0.02em;
}

.order-success__meta {
	margin-top: 4px;
	opacity: 0.75;
	font-size: 0.9rem;
}

.order-success__dot {
	margin: 0 6px;
}

.order-success__window {
	margin-top: 16px;
	padding: 14px 16px;
	border-radius: 8px;
	background: rgba(var(--v-theme-primary), 0.08);
}

.order-success__window-label {
	font-size: 0.75rem;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	opacity: 0.7;
}

.order-success__window-value {
	margin-top: 4px;
	font-size: 1.4rem;
	font-weight: 600;
}

.order-success__window-pending {
	margin-top: 6px;
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 0.9rem;
	opacity: 0.75;
}
</style>
