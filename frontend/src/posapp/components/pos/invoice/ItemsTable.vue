<template>
	<div
		ref="tableContainer"
		class="my-0 py-0 overflow-y-auto posa-items-table-container posa-responsive-table-container pos-themed-card"
		:style="containerStyles"
		:class="containerClasses"
		@dragover="onDragOverFromSelector($event)"
		@drop="onDropFromSelector($event)"
		@dragenter="onDragEnterFromSelector"
		@dragleave="onDragLeaveFromSelector"
	>
		<v-data-table
			:headers="responsiveHeaders"
			:items="items"
			item-value="posa_row_id"
			class="posa-cart-table elevation-2 pos-themed-card"
			:class="tableClasses"
			fixed-header
			:density="tableDensity"
			hide-default-footer
			:header-props="dynamicHeaderProps"
			:search="itemSearch"
			:custom-filter="customItemFilter"
		>
			<template #no-data>
				<div class="posa-cart-empty-state">
					<div class="posa-cart-empty-state__icon-wrap">
						<v-icon :icon="emptyStateIcon" size="42" class="posa-cart-empty-state__icon" />
					</div>
					<div class="posa-cart-empty-state__title">{{ emptyStateTitle }}</div>
					<div class="posa-cart-empty-state__subtitle">{{ emptyStateSubtitle }}</div>
				</div>
			</template>

			<template v-slot:item="{ item }">
				<CartItemRow
					:item="item"
					:visible-columns="finalVisibleColumns"
					:posProfile="pos_profile"
					:isReturnInvoice="isReturnInvoice"
					:invoiceType="invoiceType"
					:displayCurrency="displayCurrency"
					:formatFloat="memoizedFormatFloat"
					:formatCurrency="memoizedFormatCurrency"
					:currencySymbol="currencySymbol"
					:isNumber="isNumber"
					:isNegative="memoizedIsNegative"
					:hideQtyDecimals="hide_qty_decimals"
					:isRTL="isRtl"
					:is-expanded="isItemExpanded(item.posa_row_id)"
					@update-qty="handleQtyUpdate"
					@minus-click="handleMinusClick"
					@add-one="addOne"
					@calc-uom="calcUom"
					@update-rate="handleRateUpdate"
					@update-discount-percent="handleDiscountPercentUpdate"
					@update-discount-amount="handleDiscountAmountUpdate"
					@open-name-dialog="openNameDialog"
					@reset-item-name="resetItemName"
					@toggle-offer="toggleOffer"
					@toggle-expand="handleToggleExpand(item)"
					@remove-item="removeItem"
					@click="handleRowClick($event, item)"
				/>
			</template>
		</v-data-table>

		<v-dialog
			:model-value="Boolean(activeExpandedItem)"
			max-width="1100"
			scrollable
			@update:model-value="handleExpandedDialogToggle"
		>
			<v-card class="posa-item-details-dialog">
				<v-card-title class="d-flex align-center justify-space-between">
					<div>
						<div class="text-subtitle-1 font-weight-bold">
							{{ activeExpandedItem?.item_name || __("Item Details") }}
						</div>
						<div class="text-caption text-medium-emphasis">
							{{ activeExpandedItem?.item_code || "" }}
						</div>
					</div>
					<v-btn icon variant="text" @click="closeExpandedDialog" :aria-label="__('Close item details')">
						<v-icon>mdi-close</v-icon>
					</v-btn>
				</v-card-title>
				<v-divider></v-divider>
				<v-card-text class="posa-item-details-dialog__body">
					<ItemsTableExpandedRow
						v-if="activeExpandedItem"
						:item="activeExpandedItem"
						:is-expanded="true"
						:render-mode="'dialog'"
						:colspan="finalVisibleColumns.length"
						:pos_profile="pos_profile"
						:invoice-type="invoiceType"
						:is-return-invoice="isReturnInvoice"
						:invoice_doc="invoice_doc"
						:hide_qty_decimals="hide_qty_decimals"
						:expanded-content-classes="expandedContentClasses"
						:format-float="memoizedFormatFloat"
						:format-currency="memoizedFormatCurrency"
						:currency-symbol="currencySymbol"
						:is-number="isNumber"
						:set-formated-currency="setFormatedCurrency"
						:calc-prices="calcPrices"
						:calc-uom="calcUom"
						:change-price-list-rate="changePriceListRate"
						:get-serial-options="getSerialOptions"
						:set-serial-no="setSerialNo"
						:set-batch-qty="setBatchQty"
						:validate-due-date="validateDueDate"
						@qty-change="handleQtyChange"
					/>
				</v-card-text>
			</v-card>
		</v-dialog>

		<!-- Edit name dialog -->
		<v-dialog v-model="editNameDialog" max-width="400">
			<v-card>
				<v-card-title>{{ __("Item Name") }}</v-card-title>
				<v-card-text>
					<v-text-field v-model="editedName" :maxlength="140" />
				</v-card-text>
				<v-card-actions>
					<v-btn
						v-if="editNameTarget && editNameTarget.name_overridden"
						variant="text"
						@click="resetItemName(editNameTarget)"
						>{{ __("Reset") }}</v-btn
					>
					<v-spacer></v-spacer>
					<v-btn variant="text" @click="editNameDialog = false">{{ __("Cancel") }}</v-btn>
					<v-btn color="primary" variant="text" @click="saveItemName">{{ __("Save") }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount, onMounted, watch, getCurrentInstance } from "vue";
import { useInvoiceStore } from "../../../stores/invoiceStore";
import { loadItemSelectorSettings } from "../../../utils/itemSelectorSettings";
import { logComponentRender } from "../../../utils/perf";
import CartItemRow from "./CartItemRow.vue";
import ItemsTableExpandedRow from "./ItemsTableExpandedRow.vue";

import { useItemsTableSearch } from "../../../composables/pos/items/useItemsTableSearch";
import { useItemsTableDragDrop } from "../../../composables/pos/items/useItemsTableDragDrop";
import {
	DATA_TABLE_EXPAND_COLUMN,
	useItemsTableResponsive,
} from "../../../composables/pos/items/useItemsTableResponsive";
import { useItemsTableMerge } from "../../../composables/pos/items/useItemsTableMerge";
import { useItemsTableNameEdit } from "../../../composables/pos/items/useItemsTableNameEdit";
import { useFormatters } from "../../../composables/core/useFormatters";
import { useRtl } from "../../../composables/core/useRtl";
import { focusCartItemField, type CartShortcutField } from "../../../utils/cartFieldFocus";
import "./items-table-styles.css";

// Global declarations for Frappe
declare const __: (_str: string, _args?: any[]) => string;

interface Props {
	headers?: any[];
	expanded?: any[];
	itemsPerPage?: number;
	itemSearch?: string;
	pos_profile?: any;
	invoiceType?: string;
	stock_settings?: any;
	displayCurrency?: string;
	formatFloat: (_value: number, _precision?: number | string) => string;
	formatCurrency: (_value: number, _precision?: number | string) => string;
	currencySymbol: (_currency?: string) => string;
	isNumber: (_value: any) => boolean;
	setFormatedQty: (_item: any, _field: string, _value: any, _force?: boolean, _event?: any) => void;
	setFormatedCurrency: (_item: any, _field: string, _value: any, _force?: boolean, _event?: any) => void;
	calcPrices: (_item: any, _value: any, _event?: any) => void;
	calcUom: (_item: any, _uom: string) => void;
	setSerialNo: (_item: any) => void;
	setBatchQty: (_item: any, _event: any) => void;
	validateDueDate: (_item: any) => void;
	removeItem: (_item: any) => void;
	subtractOne: (_item: any) => void;
	addOne: (_item: any) => void;
	isReturnInvoice?: boolean;
	toggleOffer: (_item: any) => void;
	changePriceListRate: (_item: any) => void;
	isNegative: (_value: any) => boolean;
}

const props = withDefaults(defineProps<Props>(), {
	headers: () => [],
	expanded: () => [],
	isReturnInvoice: false,
});

const emit = defineEmits<{
	"update:expanded": [val: any[]];
	"show-drop-feedback": [val: boolean];
	"item-dropped": [val: boolean];
}>();

const { proxy } = getCurrentInstance() as any;
const eventBus = proxy?.eventBus;
const invoiceStore = useInvoiceStore();
const tableContainer = ref<HTMLElement | null>(null);

// Composables
const { customItemFilter } = useItemsTableSearch();
const dragDropHandlers = useItemsTableDragDrop(emit, eventBus);
const { isRtl } = useRtl();
const { memoizedFormatFloat, memoizedFormatCurrency, clearFormatCache } = useFormatters({
	formatFloat: props.formatFloat,
	formatCurrency: props.formatCurrency,
});

const responsive = useItemsTableResponsive(
	tableContainer,
	computed(() => props.headers || []),
);
const merge = useItemsTableMerge(computed(() => invoiceStore.items));
const nameEdit = useItemsTableNameEdit();

// Computed
const items = computed(() => invoiceStore.items);
const invoice_doc = computed(() => invoiceStore.invoiceDoc || {});
const hasItemSearch = computed(() => !!props.itemSearch?.trim());
const emptyStateIcon = computed(() => (hasItemSearch.value ? "mdi-cart-search" : "mdi-cart-outline"));
const emptyStateTitle = computed(() =>
	hasItemSearch.value ? __("No matching items in cart") : __("No items in cart"),
);
const emptyStateSubtitle = computed(() =>
	hasItemSearch.value
		? __("Try a different search term or clear the cart search.")
		: __("Add items from the selector to start building this sale."),
);

const memoizedIsNegative = computed(() => {
	return (value: any) => {
		if (typeof value === "number") return value < 0;
		return props.isNegative(value);
	};
});

const {
	breakpoint,
	responsiveHeaders,
	containerStyles,
	containerClasses,
	tableClasses,
	expandedContentClasses,
	tableDensity,
	containerHeight,
} = responsive;

const dynamicHeaderProps = computed(() => ({
	class: `responsive-header container-${breakpoint.value}`,
}));

const finalVisibleColumns = computed(() => [...responsiveHeaders.value, DATA_TABLE_EXPAND_COLUMN]);

const virtualScrollConfig = computed(() => {
	const itemCount = items.value?.length || 0;
	const height = containerHeight.value || 600;

	return {
		itemHeight: tableDensity.value === "compact" ? 48 : tableDensity.value === "comfortable" ? 72 : 60,
		itemsPerPage: Math.max(20, Math.ceil(height / 60) + 5),
		bufferSize: itemCount > 1000 ? 20 : itemCount > 500 ? 15 : 10,
	};
});

const hide_qty_decimals = computed(() => {
	const opts = loadItemSelectorSettings();
	return !!opts?.hide_qty_decimals;
});

// Watchers
watch(() => props.displayCurrency, clearFormatCache);
watch(() => props.pos_profile, clearFormatCache, { deep: true });

// Methods
const getSerialOptions = (item: any) => {
	if (Array.isArray(item?.filtered_serial_no_data)) {
		return item.filtered_serial_no_data;
	}
	return Array.isArray(item?.serial_no_data) ? item.serial_no_data : [];
};

const activeExpandedItem = computed(() => {
	const expandedId = Array.isArray(props.expanded) ? props.expanded[0] : null;
	if (!expandedId) {
		return null;
	}
	return items.value.find((item: any) => item?.posa_row_id === expandedId) || null;
});

const handleQtyChange = (item: any, event: any) => {
	const newQty = parseFloat(event.target.value) || 0;
	if (newQty === 0) {
		props.removeItem(item);
	} else {
		props.setFormatedQty(item, "qty", null, false, event.target.value);
	}
	eventBus?.emit("recalculate_return_discount", { defer: true });
};

const handleMinusClick = (item: any) => {
	// Replacement rows should still be removed directly.
	if (item.posa_is_replace) {
		props.removeItem(item);
		return;
	}

	// magnitude-based removal: only remove if qty magnitude <= 1
	// This handles -1 for returns and 1 for normal invoices correctly
	const absQty = Math.abs(item.qty || 0);
	if (absQty <= 1) {
		props.removeItem(item);
	} else {
		// subtract_one handles the sign-aware logic (e.g. -5 -> -4 in returns)
		props.subtractOne(item);
	}
	eventBus?.emit("recalculate_return_discount", { defer: true });
};

const handleQtyUpdate = (item: any, newQty: any) => {
	props.setFormatedQty(item, "qty", null, false, newQty);
	eventBus?.emit("recalculate_return_discount", { defer: true });
};

const handleRateUpdate = (item: any, newRate: any) => {
	props.setFormatedCurrency(item, "rate", null, false, { target: { value: newRate } });
	props.calcPrices(item, newRate, { target: { id: "rate" } });
};

const handleDiscountPercentUpdate = (item: any, newDiscount: any) => {
	props.setFormatedCurrency(item, "discount_percentage", null, false, {
		target: { value: newDiscount },
	});
	props.calcPrices(item, newDiscount, { target: { id: "discount_percentage" } });
};

const handleDiscountAmountUpdate = (item: any, newDiscount: any) => {
	props.setFormatedCurrency(item, "discount_amount", null, false, {
		target: { value: newDiscount },
	});
	props.calcPrices(item, newDiscount, { target: { id: "discount_amount" } });
};

const handleRowClick = (event: any, item: any) => {
	const target = event?.target as HTMLElement | null;
	if (target?.closest?.(
		[
			"button",
			".v-btn",
			"input",
			"textarea",
			"select",
			".v-field",
			".v-input",
			".qty-control-btn",
			".posa-cart-table__qty-counter",
			".posa-cart-table__qty-input",
			".posa-cart-table__qty-display",
			".posa-cart-table__editor-box",
			".posa-cart-table__editor-display",
			".posa-cart-table__editor-input",
			".delete-action-btn",
			".posa-cart-table__expand-btn",
		].join(","),
	)) {
		return;
	}
	handleToggleExpand(item);
};

const handleToggleExpand = (item: any) => {
	const itemId = item?.posa_row_id;
	if (!itemId) {
		return;
	}
	if (isItemExpanded(itemId)) {
		emit("update:expanded", []);
		return;
	}
	emit("update:expanded", [itemId]);
};

const closeExpandedDialog = () => {
	emit("update:expanded", []);
};

const handleExpandedDialogToggle = (isOpen: boolean) => {
	if (!isOpen) {
		closeExpandedDialog();
	}
};

const focusItemField = (index: number, field: CartShortcutField) => {
	return focusCartItemField(tableContainer.value, index, field);
};

const isItemExpanded = (itemId: any) => {
	return props.expanded?.includes(itemId);
};

// Drag and Drop delegation
const onDragOverFromSelector = (event: DragEvent) => dragDropHandlers.onDragOverFromSelector(event);
const onDragEnterFromSelector = () => dragDropHandlers.onDragEnterFromSelector();
const onDragLeaveFromSelector = (event: DragEvent) => dragDropHandlers.onDragLeaveFromSelector(event);
const onDropFromSelector = (event: DragEvent) => dragDropHandlers.onDropFromSelector(event);

// Name editing logic
const { editNameDialog, editedName, editNameTarget, openNameDialog, saveItemName, resetItemName } = nameEdit;

// Life-cycle
onMounted(() => {
	logComponentRender({ $el: tableContainer.value }, "ItemsTable", "mounted", {
		rows: items.value?.length || 0,
	});
});

onBeforeUnmount(() => {
	merge.clearMergeCache();
});

defineExpose({
	focusItemField,
});
</script>

<style>
/* Global styles for ItemsTable and its children */
@import "./items-table-styles.css";
</style>

<style scoped>
/* Scoped styles for ItemsTable component specific logic */
.posa-items-table-container {
	position: relative;
	transition: all 0.3s ease;
}

.posa-item-details-dialog {
	border-radius: 18px;
}

.posa-item-details-dialog__body {
	padding: 0 !important;
}
</style>
