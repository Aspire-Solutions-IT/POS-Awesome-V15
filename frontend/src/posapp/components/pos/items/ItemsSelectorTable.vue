<template>
	<div class="items-table-container">
		<v-data-table
			ref="tableRef"
			:headers="headers"
			:items="displayedItems"
			class="sleek-data-table"
			item-value="item_code"
			fixed-header
			height="100%"
			:items-per-page="displayedItems.length || -1"
			hide-default-footer
			:header-props="headerProps"
			:no-data-text="noDataText"
			@click:row="handleRowClick"
			:item-class="itemClass"
			:row-props="rowProps"
			@scroll.passive="handleListScroll"
		>
			<template v-slot:item.rate="{ item }">
				<div v-if="context !== 'purchase'">
					<div v-if="item.is_on_sale && item.price_before_sale != null" class="table-price-was">
						{{
							currencySymbol(
								item.original_currency ||
									item.currency ||
									item.price_list_currency ||
									posProfile.currency,
							)
						}}
						{{
							formatCurrency(
								item.price_before_sale,
								item.original_currency ||
									item.currency ||
									item.price_list_currency ||
									posProfile.currency,
								ratePrecision(item.price_before_sale),
							)
						}}
					</div>
					<div
						class="text-primary rate-cell-primary"
						:class="{ 'rate-cell-sale': item.is_on_sale && item.price_before_sale != null }"
					>
						<div>
							{{
								currencySymbol(
									item.original_currency ||
										item.currency ||
										item.price_list_currency ||
										posProfile.currency,
								)
							}}
							{{
								formatCurrency(
									item.original_rate ?? item.rate ?? 0,
									item.original_currency ||
										item.currency ||
										item.price_list_currency ||
										posProfile.currency,
									ratePrecision(item.original_rate ?? item.rate ?? 0),
								)
							}}
						</div>
						<ItemRateInfoMenu
							v-if="showRateInfo"
							:rate-info="getItemRateInfo(item)"
							:currency-symbol="currencySymbol"
							:format-currency="formatCurrency"
							:rate-precision="ratePrecision"
						/>
					</div>
					<div
						v-if="
							posProfile.posa_allow_multi_currency &&
							selectedCurrency &&
							selectedCurrency !==
								(item.original_currency ||
									item.currency ||
									item.price_list_currency ||
									posProfile.currency)
						"
						class="text-success"
					>
						{{ currencySymbol(selectedCurrency) }}
						{{ formatCurrency(item.rate, selectedCurrency, ratePrecision(item.rate)) }}
					</div>
				</div>
				<div v-else>
					<div class="text-primary rate-cell-primary">
						<div>
							{{
								currencySymbol(
									item.original_currency ||
										item.currency ||
										item.price_list_currency ||
										posProfile.currency,
								)
							}}
							{{
								formatCurrency(
									item.original_rate ?? item.rate ?? item.standard_rate ?? 0,
									item.original_currency ||
										item.currency ||
										item.price_list_currency ||
										posProfile.currency,
									ratePrecision(item.original_rate ?? item.rate ?? item.standard_rate ?? 0),
								)
							}}
						</div>
						<ItemRateInfoMenu
							v-if="showRateInfo"
							:rate-info="getItemRateInfo(item)"
							:currency-symbol="currencySymbol"
							:format-currency="formatCurrency"
							:rate-precision="ratePrecision"
						/>
					</div>
				</div>
			</template>
			<template v-slot:item.actual_qty="{ item }">
				<span class="golden--text" :class="{ 'negative-number': isNegative(item.actual_qty) }">
					{{ formatActualQty(item.actual_qty) }}
				</span>
			</template>
			<template v-slot:item.quantity_due_in="{ item }">
				<span class="golden--text" :class="{ 'negative-number': isNegative(item.quantity_due_in) }">
					{{ formatActualQty(item.quantity_due_in) }}
				</span>
			</template>
			<template v-slot:item.next_due_date="{ item }">
				<span>{{ formatDueDate(item.next_due_date) }}</span>
			</template>
		</v-data-table>
	</div>
</template>

<script setup>
import { ref } from "vue";
import ItemRateInfoMenu from "./ItemRateInfoMenu.vue";

const props = defineProps({
	displayedItems: { type: Array, default: () => [] },
	headers: { type: Array, default: () => [] },
	headerProps: { type: Object, default: () => ({}) },
	context: { type: String, default: "pos" },
	posProfile: { type: Object, default: () => ({}) },
	selectedCurrency: { type: String, default: "" },
	hideQtyDecimals: { type: Boolean, default: false },
	showRateInfo: { type: Boolean, default: true },
	currencySymbol: { type: Function, required: true },
	formatCurrency: { type: Function, required: true },
	formatNumber: { type: Function, required: true },
	ratePrecision: { type: Function, required: true },
	getItemRateInfo: { type: Function, required: true },
	isNegative: { type: Function, required: true },
	itemClass: { type: [String, Function], default: "" },
	rowProps: { type: [Object, Function], default: null },
	noDataText: { type: String, default: "" },
});

const emit = defineEmits(["row-click", "list-scroll"]);

const handleRowClick = (event, data) => {
	emit("row-click", event, data);
};

const handleListScroll = (event) => {
	emit("list-scroll", event);
};

const formatActualQty = (value) => {
	const numericQty = Number(value ?? 0);
	if (!Number.isFinite(numericQty)) {
		return 0;
	}
	if (props.hideQtyDecimals) {
		return props.formatNumber(Math.round(numericQty), 0);
	}
	return props.formatNumber(numericQty, 4);
};

const formatDueDate = (value) => {
	const normalized = String(value || "").trim();
	if (!normalized) {
		return "-";
	}
	if (window?.frappe?.datetime?.str_to_user) {
		return window.frappe.datetime.str_to_user(normalized);
	}
	return normalized;
};

const tableRef = ref(null);

const getTableElement = () => {
	const ref = tableRef.value;
	return ref?.$el || ref;
};

const scrollToIndex = (index) => {
	const ref = tableRef.value;
	const scrollToIndexFn = ref?.scrollToIndex || ref?.$?.exposed?.scrollToIndex;
	if (scrollToIndexFn) {
		scrollToIndexFn(index);
		return true;
	}

	const tableEl = getTableElement();
	const wrapper = tableEl?.querySelector?.(".v-table__wrapper");
	const rows = tableEl?.querySelectorAll?.("tbody tr");
	if (wrapper && rows && rows.length > 0) {
		const targetRow = rows[index];
		if (targetRow) {
			wrapper.scrollTop = targetRow.offsetTop;
		}
		return true;
	}
	return false;
};

defineExpose({ scrollToIndex, getTableElement, tableRef });
</script>

<style scoped>
.items-table-container {
	height: 100%;
	min-height: 0;
	display: flex;
	flex-direction: column;
	overflow: hidden;
}

:deep(.item-row-highlighted) {
	background-color: rgba(var(--v-theme-primary), 0.32);
}

:deep(.item-row-highlighted td) {
	font-weight: 600;
	color: rgb(var(--v-theme-primary));
	background-color: rgba(var(--v-theme-primary), 0.32);
}

.rate-cell-primary {
	display: inline-flex;
	align-items: center;
	gap: 4px;
}

.rate-cell-sale {
	color: var(--pos-error) !important;
}

.table-price-was {
	font-size: 0.76rem;
	font-weight: 500;
	color: var(--pos-text-secondary);
	text-decoration: line-through;
	text-decoration-thickness: 1px;
}

.sleek-data-table {
	margin: 0;
	background-color: transparent;
	border-radius: var(--pos-radius-md);
	overflow: hidden;
	border: 1px solid var(--pos-border-light);
	height: 100%;
	min-height: 0;
	display: flex;
	flex-direction: column;
	transition: all 0.3s ease;
}

.sleek-data-table:hover {
	box-shadow: 0 12px 24px var(--pos-shadow-light) !important;
}

.sleek-data-table :deep(th) {
	font-weight: 700;
	font-size: 0.8rem;
	text-transform: none;
	letter-spacing: 0.02em;
	padding: 14px 16px;
	transition: all 0.3s ease;
	border-bottom: 1px solid var(--pos-border-light);
	background: var(--pos-surface-muted);
	color: var(--pos-text-secondary);
	backdrop-filter: blur(8px);
	-webkit-backdrop-filter: blur(8px);
	box-shadow: none;
	text-shadow: none;
	font-family:
		"SF Pro Display", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "Noto Sans Arabic", "Tahoma",
		sans-serif;
	font-variant-numeric: lining-nums tabular-nums;
	font-feature-settings:
		"tnum" 1,
		"lnum" 1,
		"kern" 1;
	-webkit-font-smoothing: antialiased;
	-moz-osx-font-smoothing: grayscale;
}

:deep([data-theme="dark"]) .sleek-data-table th,
:deep(.v-theme--dark) .sleek-data-table th {
	background: var(--pos-surface-muted) !important;
	border-bottom: 1px solid var(--pos-border-light);
	color: var(--pos-text-secondary);
	text-shadow: none;
	box-shadow: none;
}

.sleek-data-table :deep(.v-data-table__wrapper),
.sleek-data-table :deep(.v-table__wrapper) {
	border-radius: var(--pos-radius-md);
	height: 100%;
	min-height: 0;
	overflow-y: auto;
	scrollbar-width: thin;
	position: relative;
	overscroll-behavior: contain;
}

.sleek-data-table :deep(.v-data-table) {
	height: 100%;
	min-height: 0;
	display: flex;
	flex-direction: column;
}

.sleek-data-table :deep(.v-data-table__wrapper tbody) {
	overflow-y: auto;
	max-height: calc(100% - 60px);
}

.sleek-data-table :deep(tr) {
	transition: all 0.2s ease;
	border-bottom: 1px solid var(--pos-border-light);
	background-color: var(--pos-surface-raised);
}

.sleek-data-table :deep(tr:hover) {
	background-color: rgba(var(--v-theme-primary), 0.05);
	transform: none;
	box-shadow: none;
}

.sleek-data-table :deep(tbody tr:nth-child(even)) {
	background-color: rgba(var(--v-theme-on-surface), 0.015);
}

.sleek-data-table :deep(td) {
	padding: 14px 16px;
	vertical-align: middle;
	color: var(--pos-text-primary);
	font-family:
		"SF Pro Display", "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "Noto Sans Arabic", "Tahoma",
		sans-serif;
	font-variant-numeric: lining-nums tabular-nums;
	font-feature-settings:
		"tnum" 1,
		"lnum" 1,
		"kern" 1;
	-webkit-font-smoothing: antialiased;
	-moz-osx-font-smoothing: grayscale;
	letter-spacing: 0.01em;
}
</style>
