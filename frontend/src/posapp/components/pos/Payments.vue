<!-- eslint-disable vue/multi-word-component-names -->
<template>
	<div :class="['payment-shell', { 'payment-shell--dialog': dialogMode }]">
		<v-card
			:class="[
				'selection mx-auto my-0 pos-themed-card payment-card',
				dialogMode ? 'payment-card--dialog' : 'mt-3',
			]"
		>
			<v-progress-linear
				:active="loading"
				:indeterminate="loading"
				absolute
				location="top"
				color="info"
			></v-progress-linear>
			<div ref="paymentContainer" class="overflow-y-auto payment-scroll">
				<div v-if="isWizardFlow" class="payment-wizard-header">
					<div class="payment-wizard-header__title">
						{{ wizardStepTitle }}
					</div>
					<div class="payment-wizard-header__track">
						<span
							v-for="step in wizardStepCount"
							:key="step"
							class="payment-wizard-header__dot"
							:class="{ 'payment-wizard-header__dot--active': currentStep >= step }"
						></span>
					</div>
				</div>
				<div
					:class="[
						'payment-sections',
						{ 'payment-sections--dialog': dialogMode },
						{
							'payment-sections--wizard-step1': dialogMode && isWizardFlow && currentStep === 1,
						},
					]"
				>
					<section v-if="showPaymentStep" class="payment-section payment-section--summary">
						<div class="payment-section__header">
							<h3 class="payment-section__title">{{ __("Payment Summary") }}</h3>
						</div>
						<PaymentSummary
							:invoice_doc="invoice_doc"
							:total_payments_display="total_payments_display"
							:diff_payment_display="diff_payment_display"
							:diff_label="diff_label"
							:diff-payment="diff_payment"
							:change_due="change_due"
							:paid_change="paid_change"
							:credit_change="credit_change"
							:paid_change_rules="paid_change_rules"
							:currencySymbol="currencySymbol"
							:formatCurrency="formatCurrency"
							:gift-card-applied-amount="giftCardAppliedAmount"
							:gift-card-code="giftCardRedemptions[0]?.gift_card_code || ''"
							:order-ref="orderRef"
							@show-paid-amount="showPaidAmount"
							@show-diff-payment="showDiffPayment"
							@show-paid-change="showPaidChange"
							@update-credit-change="handleCreditChangeUpdate"
						/>
					</section>

					<section
						v-if="is_cashback && invoice_doc && showPaymentStep"
						class="payment-section payment-section--methods"
					>
						<div class="payment-section__header">
							<h3 class="payment-section__title">{{ __("Payment Methods") }}</h3>
						</div>
						<PaymentMethods
							:payments="visiblePaymentMethods"
							:currency="invoice_doc.currency"
							:isReturn="invoice_doc.is_return"
							:requestPaymentField="request_payment_field"
							:currencySymbol="currencySymbol"
							:formatCurrency="formatCurrency"
							:isNumber="isNumber"
							:getVisibleDenominations="getVisibleDenominations"
							:isCashLikePayment="isCashLikePayment"
							:isMpesaC2bPayment="is_mpesa_c2b_payment"
							:isGiftCardPayment="isGiftCardPayment"
							@update-amount="handlePaymentAmountChange"
							@set-full-amount="set_full_amount"
							@set-denomination="setPaymentToDenomination"
							@mpesa-dialog="mpesa_c2b_dialog"
							@request-payment="request_payment"
							@set-rest-amount="set_rest_amount"
							@open-gift-card="openGiftCardDialog"
						/>
						<PaymentGiftCardSection
							:enabled="Boolean(pos_profile?.posa_use_gift_cards)"
							:expanded="giftCardInlineExpanded"
							:applied-amount="giftCardAppliedAmount"
							:card-code="giftCardCode || giftCardRedemptions[0]?.gift_card_code || ''"
							:redeem-amount="giftCardAmount"
							:balance="giftCardBalance"
							:status="giftCardStatus"
							:loading="giftCardLoading"
							:error-message="giftCardError"
							:format-currency="(value) => formatCurrency(value, invoice_doc.currency)"
							@toggle="toggleGiftCardInline"
							@update:card-code="giftCardCode = $event"
							@update:redeem-amount="giftCardAmount = $event"
							@check-balance="checkGiftCardBalance"
							@apply="applyGiftCardRedemption"
							@clear="clearGiftCardRedemption"
						/>
					</section>

					<section v-if="showFulfillmentStep" class="payment-section payment-section--adjustments">
						<div class="payment-section__header">
							<h3 class="payment-section__title">{{ __("Fulfillment Details") }}</h3>
						</div>
						<PaymentAdditionalInfo
							:invoice-doc="invoice_doc"
							:pos-profile="pos_profile"
							:invoice-type="invoiceType"
							:address-action-label="addressActionLabel"
							:shipping-address-label="shippingAddressLabel"
							:addresses="availableFulfillmentAddresses"
							:show-address-action="showAddressAction"
							:show-collect-from-store-tag="shouldUseStoreCollectionFlow"
							:show-split-delivery="showDeliverySchedulingFields"
							:show-preferred-delivery-date="preferredDeliveryDateEnabled"
							:show-collection-date="showCollectionDate"
							:collection-date="collection_date"
							:shipping-address-error="fulfillmentValidationErrors.shippingAddress"
							:preferred-delivery-date-error="fulfillmentValidationErrors.preferredDeliveryDate"
							:additional-notes-error="fulfillmentValidationErrors.additionalNotes"
							:collect-from-store-tag-label="__('Collect from Store')"
							:preferred-delivery-date="preferred_delivery_date"
							:asap-delivery="customer_unsure_delivery_date"
							:preferred-delivery-min-date="preferredDeliveryMinDate"
							:selected-shipping-address="
								shouldUseStoreCollectionFlow
									? selectedStoreCollectionAddressName || null
									: invoice_doc.shipping_address_name || null
							"
							:split-delivery="Boolean(invoice_doc.posa_split_delivery)"
							:split-delivery-warning-text="splitDeliveryWarningText"
							:hold-help-text="holdHelpText"
							:address-filter="addressFilter"
							:return-validity-enabled="returnValidityEnabled"
							:return-validity-min-date="returnValidityMinDate"
							:return-valid-upto-date="return_valid_upto_date"
							@update:return-valid-upto-date="
								(val) => {
									return_valid_upto_date = val;
									updateReturnValidUpto();
								}
							"
							@update:preferred-delivery-date="
								(val) => {
									update_preferred_delivery_date(val);
								}
							"
							@update:asap-delivery="handleAsapDeliveryToggle"
							@update:collection-date="
								(val) => {
									update_collection_date(val);
								}
							"
							@update:selected-shipping-address="handleShippingAddressSelection"
							@update:split-delivery="
								(val) => {
									invoice_doc.posa_split_delivery = val ? 1 : 0;
								}
							"
							@new-address="handlePaymentNewAddress"
						/>
						<div class="payment-next-step">
							<v-btn variant="text" color="error" @click="back_to_invoice">
								{{ __("Cancel") }}
							</v-btn>
							<v-btn color="primary" @click="proceedFromFulfillmentStep">
								{{ __("Next") }}
							</v-btn>
						</div>
					</section>

					<section
						v-if="showGroupingStep"
						class="payment-section payment-section--adjustments payment-section--grouping"
					>
						<div class="payment-section__header">
							<h3 class="payment-section__title">{{ __("Split Order Groups") }}</h3>
						</div>
						<PaymentSplitGroups
							:groups="splitOrderGroups"
							:items="invoice_doc.items || []"
							:default-group-id="defaultSplitGroupId"
							:max-groups="MAX_SPLIT_GROUPS"
							:format-currency="(value) => formatCurrency(value, invoice_doc.currency)"
							@create-group="createSplitGroup"
							@remove-group="removeSplitGroup"
							@move-item="moveSplitGroupItem"
						/>
						<div class="payment-next-step">
							<v-btn variant="text" color="primary" @click="goToFulfillmentStep">
								{{ __("Back") }}
							</v-btn>
							<v-btn
								color="primary"
								:disabled="!canProceedFromGrouping"
								@click="proceedToPaymentStep"
							>
								{{ __("Next") }}
							</v-btn>
						</div>
					</section>

					<section v-if="showPaymentStep" class="payment-section payment-section--adjustments">
						<div class="payment-section__header">
							<h3 class="payment-section__title">{{ __("Redemption and Totals") }}</h3>
						</div>
						<PaymentRedemption
							:invoice-doc="invoice_doc"
							:customer-info="customer_info"
							:pos-profile="pos_profile"
							:available-points-amount="available_points_amount"
							:loyalty-amount="loyalty_amount"
							:available-customer-credit="available_customer_credit"
							:redeem-customer-credit="redeem_customer_credit"
							:redeemed-customer-credit="redeemed_customer_credit"
							:format-currency="formatCurrency"
							:format-float="formatFloat"
							:currency-symbol="currencySymbol"
							@set-formatted-currency="handleRedemptionFormattedCurrency"
						/>
						<InvoiceTotals
							:invoice_doc="invoice_doc"
							:displayCurrency="displayCurrency"
							:diff_payment="diff_payment"
							:diff_label="diff_label"
							:currencySymbol="currencySymbol"
							:formatCurrency="formatCurrency"
						/>
						<PaymentPurchaseOrder
							:invoice-doc="invoice_doc"
							:pos-profile="pos_profile"
							:new-po-date="new_po_date"
							@update:new-po-date="
								(val) => {
									new_po_date = val;
									update_po_date();
								}
							"
						/>
					</section>

					<section v-if="showPaymentStep" class="payment-section payment-section--settlement">
						<div class="payment-section__header">
							<h3 class="payment-section__title">{{ __("Credit and Output") }}</h3>
						</div>
						<PaymentOptions
							:invoice-doc="invoice_doc"
							:pos-profile="pos_profile"
							:diff-payment="diff_payment"
							:credit-change="credit_change"
							:is-write-off-change="is_write_off_change"
							:is-credit-sale="is_credit_sale"
							:is-cashback="is_cashback"
							:is-credit-return="is_credit_return"
							:new-credit-due-date="new_credit_due_date"
							:credit-due-days="credit_due_days"
							:credit-due-presets="credit_due_presets"
							:write-off-amount="invoice_doc.write_off_amount || Math.max(diff_payment, 0)"
							:write-off-max-amount="writeOffProfileLimit"
							:redeem-customer-credit="redeem_customer_credit"
							:available-customer-credit="available_customer_credit"
							:redeemed-customer-credit="redeemed_customer_credit"
							:customer-credit-sources="customer_credit_dict.length"
							:format-currency="formatCurrency"
							@update:is-write-off-change="is_write_off_change = $event"
							@update:is-credit-sale="is_credit_sale = $event"
							@update:is-cashback="is_cashback = $event"
							@update:is-credit-return="is_credit_return = $event"
							@update:new-credit-due-date="
								(val) => {
									new_credit_due_date = val;
									update_credit_due_date();
								}
							"
							@update:credit-due-days="credit_due_days = $event"
							@update:write-off-amount="handleWriteOffAmountUpdate"
							@apply-due-preset="applyDuePreset"
							@update:redeem-customer-credit="redeem_customer_credit = $event"
							@get-available-credit="get_available_credit"
						/>
						<PaymentCustomerCreditDetails
							:invoice-doc="invoice_doc"
							:available-customer-credit="available_customer_credit"
							:redeem-customer-credit="redeem_customer_credit"
							:customer-credit-dict="customer_credit_dict"
							:credit-source-label="creditSourceLabel"
							:format-currency="formatCurrency"
							:currency-symbol="currencySymbol"
							@set-formatted-currency="
								(data) =>
									setFormatedCurrency(data.target, data.field, null, false, data.value)
							"
						/>
					</section>

					<section
						v-if="
							showPaymentStep &&
							parseBooleanSetting(pos_profile?.posa_allow_select_print_format_in_payments)
						"
						class="payment-section payment-section--meta"
					>
						<div class="payment-section__header">
							<h3 class="payment-section__title">{{ __("Print") }}</h3>
						</div>
						<PaymentSelectionFields
							:print-formats="print_formats"
							:print-format="print_format"
							:show-print-format="
								parseBooleanSetting(pos_profile?.posa_allow_select_print_format_in_payments)
							"
							@update:print-format="print_format = $event"
						/>
					</section>
				</div>
			</div>
		</v-card>

		<div v-if="showPaymentStep" :class="['payment-footer', { 'payment-footer--dialog': dialogMode }]">
			<div v-if="isWizardFlow" class="payment-wizard-actions">
				<v-btn variant="text" color="primary" @click="goToPreviousWizardStep">
					{{ __("Back") }}
				</v-btn>
			</div>
			<PaymentActionButtons
				ref="submitButton"
				:loading="loading"
				:validatePayment="validatePayment"
				:highlightSubmit="highlightSubmit"
				:compact="dialogMode"
				:show-submit-without-payment="showSubmitWithoutPayment"
				@submit="submit"
				@submit-and-print="submit(undefined, false, true)"
				@submit-without-payment="submitWithoutPaymentOrder"
				@cancel="back_to_invoice"
			/>
		</div>
		<!-- Dialogs Section (Custom Days, Phone Payment) -->
		<PaymentDialogs
			:custom-days-dialog="custom_days_dialog"
			:custom-days-value="custom_days_value"
			:phone-dialog="phone_dialog"
			:invoice-doc="invoice_doc"
			@update:custom-days-dialog="custom_days_dialog = $event"
			@update:custom-days-value="custom_days_value = $event"
			@apply-custom-days="applyCustomDays"
			@update:phone-dialog="phone_dialog = $event"
			@request-payment="request_payment"
		/>
		<MissingOrderAddressDialog
			v-model="missingOrderAddressDialog"
			@customer-collected="confirmCustomerCollectedOrder"
			@enter-address="openMissingOrderAddressEntry"
		/>
		<GiftCardDialog
			:model-value="giftCardDialogOpen"
			:card-code="giftCardCode"
			:redeem-amount="giftCardAmount"
			:balance="giftCardBalance"
			:status="giftCardStatus"
			:is-supervisor="Boolean(currentCashier?.is_supervisor)"
			:loading="giftCardLoading"
			:mode="giftCardMode"
			:error-message="giftCardError"
			@update:model-value="giftCardDialogOpen = $event"
			@update:card-code="giftCardCode = $event"
			@update:redeem-amount="giftCardAmount = $event"
			@set-mode="setGiftCardMode"
			@check-balance="checkGiftCardBalance"
			@apply-redemption="applyGiftCardRedemption"
			@issue-card="issueGiftCard"
			@top-up-card="topUpGiftCard"
		/>
	</div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, getCurrentInstance, nextTick } from "vue";
import { storeToRefs } from "pinia";

// Stores
import { useInvoiceStore } from "../../stores/invoiceStore.js";
import { useCustomersStore } from "../../stores/customersStore.js";
import { useUIStore } from "../../stores/uiStore.js";
import { useToastStore } from "../../stores/toastStore.js";
import { useSyncStore } from "../../stores/syncStore.ts";
import { useSocketStore } from "../../stores/socketStore";
import { useEmployeeStore } from "../../stores/employeeStore";

// Composables
import { usePaymentCalculations } from "../../composables/pos/payments/usePaymentCalculations";
import { usePaymentSubmission } from "../../composables/pos/payments/usePaymentSubmission";
import { useRedemptionLogic } from "../../composables/pos/payments/useRedemptionLogic";
import { usePaymentPrinting } from "../../composables/pos/payments/usePaymentPrinting";
import { usePaymentMethods } from "../../composables/pos/payments/usePaymentMethods";
import { useInvoiceDetails } from "../../composables/pos/invoice/useInvoiceDetails";
import { normalizeDateForBackend, useFormat } from "../../format";
import { isOffline, getCachedGiftCardSnapshot, saveGiftCardSnapshot } from "../../../offline/index";
import GiftCardDialog from "./wallet/GiftCardDialog.vue";
import {
	initializePaymentLinesForDialog,
	rebalancePreferredPaymentLine,
	resolvePreferredPaymentLine,
} from "../../utils/paymentInitialization";
import { resolvePaymentPrintFormatDoctypes } from "../../utils/paymentPrintDoctype";
import { resolvePaymentPrintFormat } from "../../utils/paymentPrintFormat";
import { parseBooleanSetting } from "../../utils/stock";

// Components
import PaymentSummary from "./payments/PaymentSummary.vue";
import InvoiceTotals from "./payments/InvoiceTotals.vue";
import PaymentActionButtons from "./payments/PaymentActionButtons.vue";
import PaymentMethods from "./payments/PaymentMethods.vue";
import PaymentGiftCardSection from "./payments/PaymentGiftCardSection.vue";
import PaymentRedemption from "./payments/PaymentRedemption.vue";
import PaymentAdditionalInfo from "./payments/PaymentAdditionalInfo.vue";
import PaymentSplitGroups from "./payments/PaymentSplitGroups.vue";
import PaymentPurchaseOrder from "./payments/PaymentPurchaseOrder.vue";
import PaymentCustomerCreditDetails from "./payments/PaymentCustomerCreditDetails.vue";
import PaymentOptions from "./payments/PaymentOptions.vue";
import PaymentSelectionFields from "./payments/PaymentSelectionFields.vue";
import PaymentDialogs from "./payments/PaymentDialogs.vue";
import MissingOrderAddressDialog from "./payments/MissingOrderAddressDialog.vue";

const props = defineProps({
	dialogMode: {
		type: Boolean,
		default: false,
	},
});

const { proxy } = getCurrentInstance();
const eventBus = proxy.eventBus;
const __ = window.__;
const frappe = window.frappe;

const invoiceStore = useInvoiceStore();
const customersStore = useCustomersStore();
const uiStore = useUIStore();
const toastStore = useToastStore();
const syncStore = useSyncStore();
const socketStore = useSocketStore();

// Destructure format utilities
const {
	currency_precision,
	formatCurrency,
	formatFloat,
	currencySymbol,
	isNumber,
	flt,
	setFormatedCurrency,
} = useFormat();

const { selectedCustomer, customerInfo } = storeToRefs(customersStore);
const { activeView, paymentDialogOpen } = storeToRefs(uiStore);
const { invoiceType, deliveryCharges, selectedDeliveryCharge } = storeToRefs(invoiceStore);
const employeeStore = useEmployeeStore();
const { currentCashier } = storeToRefs(employeeStore);

// State
const is_return = ref(false);
const is_credit_sale = ref(false);
const is_write_off_change = ref(false);
const redeem_customer_credit = ref(false);
const pos_profile = ref("");
const stock_settings = ref("");
const pos_settings = ref({});
const is_cashback = ref(true);
const paid_change = ref(0);
const credit_change = ref(0);
const loading = ref(false);
const show_change_dialog = ref(false);
const is_credit_return = ref(false);
const customer_info = ref("");
const print_format = ref("");
const print_formats = ref([]);
const paid_change_rules = ref([]);
const is_user_editing_paid_change = ref(false);
const highlightSubmit = ref(false);
const last_payment_change_was_cash = ref(null);
const backgroundStatusCheck = ref(null);
const paymentVisible = ref(false);
const paymentContainer = ref(null);
const submitButton = ref(null);
const _shortcutHandlers = ref({});
const submissionInFlight = ref(false);
const queuedShortcutSubmit = ref(null);
const missingOrderAddressDialog = ref(false);
const fulfillmentValidationVisible = ref(false);
const pendingMissingAddressSubmit = ref(null);
const pendingCollectedAddressSubmit = ref(false);
const storeCollectionAddresses = ref([]);
const selectedStoreCollectionAddressName = ref(null);
const defaultSplitGroupId = "default";
const MAX_SPLIT_GROUPS = 4;
const currentStep = ref(1);
const customer_unsure_delivery_date = ref(true);
const hold_release_date = ref(null);
const giftCardDialogOpen = ref(false);
const giftCardInlineExpanded = ref(false);
const activeGiftCardPayment = ref(null);
const giftCardCode = ref("");
const giftCardAmount = ref(0);
const giftCardBalance = ref(0);
const giftCardStatus = ref("");
const giftCardLoading = ref(false);
const giftCardMode = ref("redeem");
const giftCardError = ref("");
const giftCardRedemptions = ref([]);

// Computed Properties
const invoice_doc = computed({
	get: () => invoiceStore.invoiceDoc || {},
	set: (value) => invoiceStore.setInvoiceDoc(value),
});

const displayCurrency = computed(() => (invoice_doc.value ? invoice_doc.value.currency : ""));
const isPaymentOpen = computed(() => activeView.value === "payment" || paymentDialogOpen.value);
const netInvoiceSettlementAmount = computed(() => {
	if (!invoice_doc.value) return 0;

	const invoiceTotal = flt(
		invoice_doc.value.rounded_total || invoice_doc.value.grand_total,
		currency_precision.value,
	);
	const coveredAmount = flt(
		(invoice_doc.value?.loyalty_amount || loyalty_amount.value || 0) +
			(redeemed_customer_credit.value || 0),
		currency_precision.value,
	);

	const net = invoiceTotal - coveredAmount;
	return invoice_doc.value?.is_return ? Math.min(net, 0) : Math.max(net, 0);
});

const needsFulfillmentStep = computed(
	() => invoiceType.value === "Order" && Boolean(pos_profile.value?.posa_create_only_sales_order),
);
const isWizardFlow = computed(() => needsFulfillmentStep.value);
const isSplitDeliveryEnabled = computed(
	() => Boolean(invoice_doc.value?.posa_split_delivery) && invoiceType.value === "Order",
);
const wizardStepCount = computed(() => (isSplitDeliveryEnabled.value ? 3 : 2));
const wizardStepTitle = computed(() => {
	if (currentStep.value === 1) {
		return __("Step 1 of {0}: Fulfillment", [wizardStepCount.value]);
	}
	if (isSplitDeliveryEnabled.value && currentStep.value === 2) {
		return __("Step 2 of 3: Grouping");
	}
	return __("Step {0} of {1}: Payment", [wizardStepCount.value, wizardStepCount.value]);
});

const isCollectFromStoreSelected = () => {
	const selectedName = String(
		invoice_doc.value?.posa_delivery_charges || selectedDeliveryCharge.value || "",
	).trim();
	if (!selectedName) {
		return false;
	}
	const selectedRow = (Array.isArray(deliveryCharges.value) ? deliveryCharges.value : []).find(
		(row) => String(row?.name || "").trim() === selectedName,
	);
	const collectFromStoreFlag = selectedRow?.collect_from_store;
	return collectFromStoreFlag === 1 || collectFromStoreFlag === "1" || collectFromStoreFlag === true;
};

const shouldUseStoreCollectionFlow = computed(
	() => !isCollectionDeliveryChargeSelected() && isCollectFromStoreSelected(),
);

const showDeliverySchedulingFields = computed(
	() => !isCollectionDeliveryChargeSelected() && !shouldUseStoreCollectionFlow.value,
);

const availableFulfillmentAddresses = computed(() =>
	shouldUseStoreCollectionFlow.value ? storeCollectionAddresses.value : addresses.value,
);

const selectedFulfillmentAddress = computed(() => {
	const selectedAddressName = shouldUseStoreCollectionFlow.value
		? String(selectedStoreCollectionAddressName.value || "").trim()
		: String(invoice_doc.value?.shipping_address_name || "").trim();
	if (!selectedAddressName) {
		return null;
	}
	return (
		(Array.isArray(availableFulfillmentAddresses.value) ? availableFulfillmentAddresses.value : []).find(
			(addr) => String(addr?.name || "").trim() === selectedAddressName,
		) || null
	);
});

const hasAddressValue = (address, key) => Boolean(String(address?.[key] || "").trim());

const hasFulfillmentAddress = computed(() => {
	const selectedAddress = selectedFulfillmentAddress.value;
	if (!selectedAddress) {
		return false;
	}

	return hasAddressValue(selectedAddress, "name");
});

const hasFulfillmentNotes = computed(() => Boolean(String(invoice_doc.value?.posa_notes || "").trim()));

const splitDeliveryWarningText = computed(() => {
	const notes = String(invoice_doc.value?.posa_notes || "").trim();
	if (!notes) {
		return "";
	}

	const hasSplitInNotes = /\bsplit\b/i.test(notes);
	const splitDeliverySelected =
		invoice_doc.value?.posa_split_delivery === 1 ||
		invoice_doc.value?.posa_split_delivery === "1" ||
		invoice_doc.value?.posa_split_delivery === true;

	if (!hasSplitInNotes || splitDeliverySelected) {
		return "";
	}

	return __("Split is in the notes but the Split Delivery box is not ticked.");
});

const createDefaultSplitGroup = (rowIds = []) => ({
	group_id: defaultSplitGroupId,
	label: __("Group 1"),
	row_ids: [...rowIds],
});

const normalizeSplitGroupLabel = (label, index) => {
	const normalized = String(label || "").trim();
	return normalized || __("Group {0}", [index + 1]);
};

const normalizeSplitGroupsState = (rawGroups, items = []) => {
	const itemRowIds = (Array.isArray(items) ? items : [])
		.map((item) => String(item?.posa_row_id || "").trim())
		.filter(Boolean);
	const itemRowIdSet = new Set(itemRowIds);
	const groups = [];
	const assigned = new Set();

	(Array.isArray(rawGroups) ? rawGroups : []).forEach((entry, index) => {
		if (!entry || typeof entry !== "object") {
			return;
		}
		const groupId = String(entry.group_id || "").trim();
		if (!groupId) {
			return;
		}
		const rowIds = [];
		(entry.row_ids || []).forEach((rowId) => {
			const normalizedRowId = String(rowId || "").trim();
			if (!normalizedRowId || !itemRowIdSet.has(normalizedRowId) || assigned.has(normalizedRowId)) {
				return;
			}
			assigned.add(normalizedRowId);
			rowIds.push(normalizedRowId);
		});
		groups.push({
			group_id: groupId,
			label: normalizeSplitGroupLabel(entry.label, index),
			row_ids: rowIds,
		});
	});

	let defaultGroup = groups.find((group) => group.group_id === defaultSplitGroupId);
	if (!defaultGroup) {
		defaultGroup = createDefaultSplitGroup();
		groups.unshift(defaultGroup);
	}

	itemRowIds.forEach((rowId) => {
		if (!assigned.has(rowId)) {
			defaultGroup.row_ids.push(rowId);
		}
	});

	return groups;
};

const syncSplitGroupsState = () => {
	if (!invoice_doc.value) {
		return;
	}
	if (!isSplitDeliveryEnabled.value) {
		invoice_doc.value.posa_split_groups = [];
		return;
	}

	const normalized = normalizeSplitGroupsState(
		invoice_doc.value.posa_split_groups,
		invoice_doc.value.items || [],
	);
	invoice_doc.value.posa_split_groups = normalized;
};

const splitOrderGroups = computed(() =>
	normalizeSplitGroupsState(invoice_doc.value?.posa_split_groups, invoice_doc.value?.items || []),
);

const canProceedFromGrouping = computed(() => {
	const itemRowIds = (invoice_doc.value?.items || [])
		.map((item) => String(item?.posa_row_id || "").trim())
		.filter(Boolean);
	const assignedRowIds = splitOrderGroups.value.flatMap((group) => group.row_ids || []);
	return itemRowIds.length > 0 && assignedRowIds.length === itemRowIds.length;
});

const orderRefRequestInFlight = ref(false);

const ensureOrderRef = () => {
	if (!invoice_doc.value || invoiceType.value !== "Order") {
		return;
	}

	const existingOrderRef = String(invoice_doc.value.customer_order_ref || "").trim();
	if (existingOrderRef || orderRefRequestInFlight.value) {
		return;
	}

	orderRefRequestInFlight.value = true;
	frappe.call({
		method: "posawesome.posawesome.api.sales_orders.get_unique_order_ref",
		args: {
			sales_order_name: invoice_doc.value?.name || null,
		},
		async: true,
		callback: (response) => {
			orderRefRequestInFlight.value = false;
			const generatedOrderRef = String(response?.message || "").trim();
			if (generatedOrderRef && invoice_doc.value && invoiceType.value === "Order") {
				invoice_doc.value.customer_order_ref = generatedOrderRef;
			}
		},
		error: () => {
			orderRefRequestInFlight.value = false;
			toastStore.show({
				title: __("Unable to generate order ref"),
				color: "warning",
			});
		},
	});
};

const orderRef = computed(() => String(invoice_doc.value?.customer_order_ref || "").trim());

const hasCreditCardPayment = () => {
	const payments = Array.isArray(invoice_doc.value?.payments) ? invoice_doc.value.payments : [];
	return payments.some((payment) => {
		const amount = flt(payment?.amount || 0);
		if (amount <= 0) {
			return false;
		}

		const modeOfPayment = String(payment?.mode_of_payment || "")
			.trim()
			.toLowerCase();
		const paymentType = String(payment?.type || "")
			.trim()
			.toLowerCase();

		return modeOfPayment.includes("credit card") || paymentType.includes("credit card");
	});
};

const hasValidRevolutReference = () => {
	const currentRef = String(invoice_doc.value?.customer_order_ref || "").trim();
	return currentRef.startsWith("#");
};

const requestRevolutReference = () =>
	new Promise((resolve) => {
		let settled = false;
		let submittingReference = false;
		const promptZIndex = 2400;
		const finish = (result) => {
			if (settled) {
				return;
			}
			settled = true;
			resolve(result);
		};
		const currentValue = String(invoice_doc.value?.customer_order_ref || "").trim();
		const dialog = frappe.prompt(
			[
				{
					fieldname: "revolut_reference",
					fieldtype: "Data",
					label: __("Revolut Reference"),
					reqd: 1,
					default: currentValue.startsWith("#") ? currentValue : "#",
					description: __("Enter the Revolut reference starting with #"),
				},
			],
			(values) => {
				submittingReference = true;
				const enteredReference = String(values?.revolut_reference || "").trim();
				if (!enteredReference.startsWith("#")) {
					frappe.msgprint({
						title: __("Invalid Revolut Reference"),
						message: __("The Revolut reference must start with #"),
						indicator: "red",
					});
					finish(false);
					return;
				}

				if (invoice_doc.value) {
					invoice_doc.value.customer_order_ref = enteredReference;
				}
				finish(true);
			},
			__("Revolut Reference Required"),
			__("Continue"),
		);
		if (dialog) {
			dialog.$wrapper?.css("z-index", promptZIndex);
			dialog.$wrapper?.on("shown.bs.modal", () => {
				dialog.$wrapper?.css("z-index", promptZIndex);
				dialog.get_primary_btn?.()?.off(".revolut-reference");
				dialog
					.get_primary_btn?.()
					?.on("click.revolut-reference mousedown.revolut-reference", () => {
						submittingReference = true;
					});
				window
					.$(".modal-backdrop")
					.last()
					.css("z-index", promptZIndex - 1);
			});
			dialog.onhide = () => {
				if (!submittingReference) {
					finish(false);
				}
			};
		}
	});

const ensureRequiredRevolutReference = async () => {
	if (invoiceType.value !== "Order" || !hasCreditCardPayment() || hasValidRevolutReference()) {
		return true;
	}

	const provided = await requestRevolutReference();
	if (!provided) {
		toastStore.show({
			title: __("Submission cancelled"),
			detail: __("A Revolut reference starting with # is required for credit card payments."),
			color: "warning",
		});
	}
	return provided;
};

const hasPreferredDeliverySelection = computed(() => {
	if (!showDeliverySchedulingFields.value) {
		return true;
	}
	if (customer_unsure_delivery_date.value) {
		return true;
	}
	return Boolean(
		String(
			preferred_delivery_date.value ||
				invoice_doc.value?.prefered_earliest_delivery_date ||
				invoice_doc.value?.preferred_earliest_delivery_date ||
				"",
		).trim(),
	);
});

const isPeterboroughProfile = computed(() => String(pos_profile.value?.name || "").trim() === "Peterborough");

const showCollectionDate = computed(
	() => isPeterboroughProfile.value && isCollectFromStoreSelected(),
);

const hasOnlyNsItemsForCollection = computed(() => {
	if (!isCollectionDeliveryChargeSelected() || isPeterboroughProfile.value) {
		return true;
	}
	const lines = Array.isArray(invoice_doc.value?.items) ? invoice_doc.value.items : [];
	return lines.every((line) => {
		const itemCode = String(line?.item_code || "").trim();
		if (!itemCode) {
			return false;
		}
		return itemCode.toLowerCase().startsWith("ns");
	});
});

const fulfillmentValidationErrors = computed(() => {
	if (!fulfillmentValidationVisible.value) {
		return {
			shippingAddress: "",
			preferredDeliveryDate: "",
			additionalNotes: "",
		};
	}

	return {
		shippingAddress: hasFulfillmentAddress.value ? "" : __("Shipping address is required."),
		preferredDeliveryDate: hasPreferredDeliverySelection.value
			? ""
			: __("Earliest delivery date is required."),
		additionalNotes: hasFulfillmentNotes.value ? "" : __("Additional notes are required."),
	};
});

const canProceedToPayment = computed(() => {
	if (!needsFulfillmentStep.value) {
		return true;
	}
	return (
		hasFulfillmentAddress.value &&
		hasFulfillmentNotes.value &&
		hasOnlyNsItemsForCollection.value &&
		hasPreferredDeliverySelection.value
	);
});

const showFulfillmentStep = computed(() => !isWizardFlow.value || currentStep.value === 1);
const showGroupingStep = computed(
	() => isWizardFlow.value && isSplitDeliveryEnabled.value && currentStep.value === 2,
);
const showPaymentStep = computed(
	() => !isWizardFlow.value || currentStep.value === (isSplitDeliveryEnabled.value ? 3 : 2),
);

const validatePayment = computed(() => {
	return false;
});

const showSubmitWithoutPayment = computed(
	() => invoiceType.value === "Order" && Boolean(pos_profile.value?.posa_create_only_sales_order),
);

const getWriteOffLimit = (profile) => {
	if (!profile) return null;

	const possibleLimitFields = [
		"write_off_limit",
		"posa_max_write_off_amount",
		"max_write_off_amount",
		"write_off_amount",
		"posa_write_off_limit",
	];

	for (const field of possibleLimitFields) {
		const rawValue = profile?.[field];
		if (rawValue === undefined || rawValue === null || rawValue === "") {
			continue;
		}

		const parsed = flt(rawValue, currency_precision.value);
		if (parsed > 0) {
			return parsed;
		}
	}

	return null;
};

const writeOffProfileLimit = computed(() => getWriteOffLimit(pos_profile.value));

const request_payment_field = computed(() => {
	return (
		pos_settings.value?.invoice_fields?.some(
			(el) => el.fieldtype === "Button" && el.fieldname === "request_for_payment",
		) || false
	);
});

const returnValidityEnabled = computed(() => {
	return Boolean(
		pos_profile.value?.posa_enable_return_validity || pos_settings.value?.posa_enable_return_validity,
	);
});

const returnValidityMinDate = computed(() => {
	const postingDate = invoice_doc.value?.posting_date || frappe.datetime?.nowdate?.();
	if (!postingDate) {
		return new Date();
	}
	const parsed = new Date(postingDate);
	if (Number.isNaN(parsed.getTime())) {
		return new Date();
	}
	return parsed;
});

const preferredDeliveryMinDate = computed(() => {
	const postingDate = invoice_doc.value?.posting_date || frappe.datetime?.nowdate?.();
	const baseDate = parseDateOnly(postingDate) || new Date();
	return addDays(baseDate, 4) || baseDate;
});

const parseDateOnly = (value) => {
	if (!value) {
		return null;
	}
	const normalized = String(value).trim();
	const match = normalized.match(/^(\d{4})-(\d{2})-(\d{2})$/);
	if (!match) {
		return null;
	}
	const [, year, month, day] = match;
	const parsed = new Date(Number(year), Number(month) - 1, Number(day));
	if (Number.isNaN(parsed.getTime())) {
		return null;
	}
	parsed.setHours(0, 0, 0, 0);
	return parsed;
};

const formatDateOnly = (value) => {
	if (!(value instanceof Date) || Number.isNaN(value.getTime())) {
		return null;
	}
	const year = value.getFullYear();
	const month = String(value.getMonth() + 1).padStart(2, "0");
	const day = String(value.getDate()).padStart(2, "0");
	return `${year}-${month}-${day}`;
};

const formatDateForUkDisplay = (value) => {
	const parsed = parseDateOnly(value);
	if (!parsed) {
		return String(value || "").trim();
	}
	const day = String(parsed.getDate()).padStart(2, "0");
	const month = String(parsed.getMonth() + 1).padStart(2, "0");
	const year = parsed.getFullYear();
	return `${day}-${month}-${year}`;
};

const addDays = (value, days) => {
	if (!(value instanceof Date) || Number.isNaN(value.getTime())) {
		return null;
	}
	const next = new Date(value);
	next.setDate(next.getDate() + days);
	next.setHours(0, 0, 0, 0);
	return next;
};

const preferredDeliveryDateDate = computed(() =>
	parseDateOnly(
		preferred_delivery_date.value ||
			invoice_doc.value?.prefered_earliest_delivery_date ||
			invoice_doc.value?.preferred_earliest_delivery_date,
	),
);

const preferredDeliveryLeadDays = computed(() => {
	const preferredDate = preferredDeliveryDateDate.value;
	const baseDate = parseDateOnly(invoice_doc.value?.posting_date || frappe.datetime?.nowdate?.());
	if (!preferredDate || !baseDate) {
		return null;
	}
	const millisecondsPerDay = 24 * 60 * 60 * 1000;
	return Math.round((preferredDate.getTime() - baseDate.getTime()) / millisecondsPerDay);
});

const autoHoldFromPreferredDelivery = computed(() => {
	if (invoiceType.value !== "Order") {
		return false;
	}
	if (customer_unsure_delivery_date.value) {
		return false;
	}
	const leadDays = preferredDeliveryLeadDays.value;
	return Number.isFinite(leadDays) && leadDays > 14;
});

const autoHoldReleaseDate = computed(() => {
	if (!autoHoldFromPreferredDelivery.value) {
		return null;
	}
	return formatDateOnly(addDays(preferredDeliveryDateDate.value, -5));
});

const effectiveHoldOrder = computed(() =>
	Boolean(autoHoldFromPreferredDelivery.value || isPartialPaymentOrder.value),
);

const holdHelpText = computed(() => {
	if (autoHoldFromPreferredDelivery.value && autoHoldReleaseDate.value) {
		return __("Automatically on hold. Auto release will be set to {0}.", [
			formatDateForUkDisplay(autoHoldReleaseDate.value),
		]);
	}
	if (autoHoldFromPreferredDelivery.value) {
		return __("Automatically on hold because the preferred delivery date is more than 2 weeks away.");
	}
	if (isPartialPaymentOrder.value) {
		return __("Automatically on hold because only a partial payment has been received.");
	}
	return "";
});

const getDefaultPreferredDeliveryDate = () => {
	const baseDate =
		parseDateOnly(invoice_doc.value?.posting_date || frappe.datetime?.nowdate?.()) || new Date();
	return formatDateOnly(addDays(baseDate, 4));
};

const applyDefaultPreferredDeliveryDate = () => {
	if (!invoice_doc.value || invoiceType.value !== "Order") {
		return;
	}
	if (!showDeliverySchedulingFields.value || !preferredDeliveryDateEnabled.value) {
		return;
	}
	if (customer_unsure_delivery_date.value) {
		return;
	}
	const existingDate = String(
		preferred_delivery_date.value ||
			invoice_doc.value.prefered_earliest_delivery_date ||
			invoice_doc.value.preferred_earliest_delivery_date ||
			"",
	).trim();
	if (existingDate) {
		return;
	}
	const defaultDate = getDefaultPreferredDeliveryDate();
	if (!defaultDate) {
		return;
	}
	preferred_delivery_date.value = defaultDate;
	invoice_doc.value.prefered_earliest_delivery_date = defaultDate;
	invoice_doc.value.preferred_earliest_delivery_date = defaultDate;
};

const handleAsapDeliveryToggle = (val) => {
	customer_unsure_delivery_date.value = Boolean(val);
	if (customer_unsure_delivery_date.value) {
		preferred_delivery_date.value = null;
		if (invoice_doc.value) {
			invoice_doc.value.prefered_earliest_delivery_date = null;
			invoice_doc.value.preferred_earliest_delivery_date = null;
		}
	}
};

// Logic Composables
const {
	loyalty_amount,
	redeemed_customer_credit,
	customer_credit_dict,
	available_customer_credit,
	available_points_amount,
	get_available_credit,
} = useRedemptionLogic({
	invoiceDoc: computed(() => invoiceStore.invoiceDoc),
	posProfile: pos_profile,
	customerInfo: customer_info,
	currencyPrecision: currency_precision,
	formatFloat: (val, prec) => flt(val, prec),
	stores: { toastStore },
	onClearAmounts: () => {},
});

const { loadPrintPage, printOfflineInvoice } = usePaymentPrinting({
	invoiceDoc: computed(() => invoiceStore.invoiceDoc),
	posProfile: pos_profile,
	invoiceType: invoiceType,
	printFormat: print_format,
});

const paymentCalculations = usePaymentCalculations({
	invoiceDoc: computed(() => invoiceStore.invoiceDoc),
	posProfile: pos_profile,
	currencyPrecision: currency_precision,
	loyaltyAmount: loyalty_amount,
	redeemedCustomerCredit: redeemed_customer_credit,
	customerCreditDict: customer_credit_dict,
	customerInfo: customer_info,
	giftCardRedemptions,
	formatCurrency: (val, _curr) => formatCurrency(val, currency_precision.value),
});

const { diff_payment, total_payments, total_payments_display, diff_payment_display, diff_label, change_due } =
	paymentCalculations;

const isPartialPaymentOrder = computed(() => {
	if (invoiceType.value !== "Order" || !pos_profile.value?.posa_create_only_sales_order) {
		return false;
	}
	return total_payments.value > 0 && diff_payment.value > 0.001;
});

const {
	phone_dialog,
	get_mpesa_modes,
	is_mpesa_c2b_payment,
	mpesa_c2b_dialog,
	set_mpesa_payment,
	set_full_amount,
	set_rest_amount,
	request_payment,
	autoBalancePayments,
	getVisibleDenominations,
	isCashLikePayment,
} = usePaymentMethods({
	invoiceDoc: computed(() => invoiceStore.invoiceDoc),
	posProfile: pos_profile,
	diffPayment: diff_payment,
	getNetInvoiceAmount: () => netInvoiceSettlementAmount.value,
	formatFloat: (val) => flt(val, currency_precision.value),
	stores: {
		toastStore,
		uiStore,
	},
	eventBus: eventBus,
	onSubmit: (args, submitPrint) => {
		submitInvoiceWrapper(submitPrint, {
			onPrint: (doc, printOptions = {}) => {
				if (submitPrint) {
					if (printOptions.waitForPostSubmitPayments || printOptions.waitForInvoiceProcessing) {
						void runDeferredPrintWorkflow({
							name: printOptions.name || doc?.name,
							doctype: printOptions.doctype,
							waitForPostSubmitPayments: Boolean(printOptions.waitForPostSubmitPayments),
							waitForInvoiceProcessing: Boolean(printOptions.waitForInvoiceProcessing),
						});
					} else if (isOffline()) {
						printOfflineInvoice(doc);
					} else {
						loadPrintPage({
							doc,
							doctype: printOptions.doctype,
						});
					}
				}
			},
			onSuccess: () => {
				eventBus.emit("focus_item_search");
			},
		});
	},
	setRedeemCustomerCredit: (val) => {
		redeem_customer_credit.value = val;
	},
	customerCreditDict: customer_credit_dict,
	redeemedCustomerCredit: redeemed_customer_credit,
	isCashback: is_cashback,
	getTotalChange: () => Math.max(-diff_payment.value, 0),
	getPaidChange: () => paid_change.value,
	getCreditChange: () => credit_change.value,
	onBackToInvoice: () => eventBus.emit("change_active_view", "Invoice"),
});

const {
	addresses,
	new_delivery_date,
	preferred_delivery_date,
	collection_date,
	new_po_date,
	new_credit_due_date,
	credit_due_days,
	credit_due_presets,
	custom_days_dialog,
	custom_days_value,
	return_valid_upto_date,
	get_addresses,
	new_address,
	addressFilter,
	normalizeAddress,
	update_delivery_date,
	update_preferred_delivery_date,
	update_collection_date,
	update_po_date,
	update_credit_due_date,
	applyDuePreset,
	applyCustomDays,
	initializeReturnValidity,
	updateReturnValidUpto,
	formatDateDisplay,
} = useInvoiceDetails({
	invoiceDoc: computed(() => invoiceStore.invoiceDoc),
	posProfile: pos_profile,
	invoiceType: invoiceType,
	posSettings: pos_settings,
	stores: {
		toastStore,
		invoiceStore,
	},
	eventBus: eventBus,
});

const preferredDeliveryDateEnabled = computed(() => {
	const setting = pos_profile.value?.posa_enable_preferred_delivery_date;
	return (
		showDeliverySchedulingFields.value &&
		!(setting === 0 || setting === "0" || setting === false)
	);
});

const { ensureReturnPaymentsAreNegative, restoreReturnPayments, validateSubmission, submitInvoice } =
	usePaymentSubmission({
		invoiceDoc: computed(() => invoiceStore.invoiceDoc),
		posProfile: pos_profile,
		stockSettings: stock_settings,
		invoiceType: invoiceType,
		is_write_off_change: is_write_off_change,
		isCashback: is_cashback,
		paidChange: paid_change,
		creditChange: credit_change,
		redeemedCustomerCredit: redeemed_customer_credit,
		customerCreditDict: customer_credit_dict,
		giftCardRedemptions: giftCardRedemptions,
		diff_payment: diff_payment,
		is_credit_sale: is_credit_sale,
		loyaltyAmount: loyalty_amount,
		isCollectionDeliveryChargeSelected: computed(() => isCollectionDeliveryChargeSelected()),
		isSplitGroupedOrder: computed(
			() => isSplitDeliveryEnabled.value && splitOrderGroups.value.length > 0,
		),
		formatFloat: (val, prec) => flt(val, prec),
		stores: {
			toastStore,
			syncStore,
			customersStore,
			uiStore,
			invoiceStore,
		},
		currencyPrecision: currency_precision,
	});

const isGiftCardPayment = (payment) => {
	if (!pos_profile.value?.posa_use_gift_cards) {
		return false;
	}
	return String(payment?.mode_of_payment || "")
		.trim()
		.toLowerCase()
		.includes("gift");
};

const visiblePaymentMethods = computed(() =>
	(Array.isArray(invoice_doc.value?.payments) ? invoice_doc.value.payments : []).filter(
		(payment) => !isGiftCardPayment(payment),
	),
);

const giftCardAppliedAmount = computed(() =>
	(Array.isArray(giftCardRedemptions.value) ? giftCardRedemptions.value : []).reduce(
		(sum, row) => sum + flt(row?.amount || 0, currency_precision.value),
		0,
	),
);

const resetGiftCardState = ({ clearPayment = false } = {}) => {
	giftCardDialogOpen.value = false;
	giftCardInlineExpanded.value = false;
	giftCardCode.value = "";
	giftCardAmount.value = 0;
	giftCardBalance.value = 0;
	giftCardStatus.value = "";
	giftCardLoading.value = false;
	giftCardMode.value = "redeem";
	giftCardError.value = "";
	giftCardRedemptions.value = [];
	if (clearPayment && activeGiftCardPayment.value) {
		activeGiftCardPayment.value.amount = 0;
		if (activeGiftCardPayment.value.base_amount !== undefined) {
			activeGiftCardPayment.value.base_amount = 0;
		}
	}
	activeGiftCardPayment.value = null;
};

const setGiftCardMode = (mode) => {
	giftCardMode.value = mode || "redeem";
	giftCardError.value = "";
};

const getGiftCardRemainingAmount = () => {
	const flexiblePayment =
		activeGiftCardPayment.value || resolvePreferredPaymentLine(invoice_doc.value, isCashLikePayment);
	const payments = Array.isArray(invoice_doc.value?.payments) ? invoice_doc.value.payments : [];
	const otherPaymentsTotal = payments.reduce((sum, payment) => {
		if (!payment || payment === flexiblePayment) {
			return sum;
		}
		return sum + flt(payment.amount || 0, currency_precision.value);
	}, 0);
	return Math.max(flt(netInvoiceSettlementAmount.value - otherPaymentsTotal, currency_precision.value), 0);
};

const clearGiftCardRedemption = () => {
	if (activeGiftCardPayment.value) {
		activeGiftCardPayment.value.amount = 0;
		if (activeGiftCardPayment.value.base_amount !== undefined) {
			activeGiftCardPayment.value.base_amount = 0;
		}
	}
	giftCardRedemptions.value = [];
	giftCardCode.value = "";
	giftCardAmount.value = 0;
	giftCardBalance.value = 0;
	giftCardStatus.value = "";
	giftCardError.value = "";
	giftCardInlineExpanded.value = false;
	rebalancePreferredPaymentCoverage(0);
};

const toggleGiftCardInline = () => {
	giftCardInlineExpanded.value = !giftCardInlineExpanded.value;
	activeGiftCardPayment.value = null;
	if (giftCardInlineExpanded.value) {
		giftCardCode.value = giftCardRedemptions.value[0]?.gift_card_code || giftCardCode.value || "";
		giftCardAmount.value = flt(
			giftCardRedemptions.value[0]?.amount || giftCardAmount.value || 0,
			currency_precision.value,
		);
	} else {
		giftCardError.value = "";
	}
};

const openGiftCardDialog = (payment = null) => {
	activeGiftCardPayment.value = payment;
	giftCardDialogOpen.value = true;
	giftCardCode.value = giftCardRedemptions.value[0]?.gift_card_code || "";
	giftCardAmount.value = flt(
		giftCardRedemptions.value[0]?.amount || payment?.amount || 0,
		currency_precision.value,
	);
	giftCardBalance.value = flt(giftCardBalance.value || 0, currency_precision.value);
	giftCardStatus.value = giftCardStatus.value || "";
	giftCardMode.value = "redeem";
	giftCardError.value = "";
};

const checkGiftCardBalance = async () => {
	if (!giftCardCode.value || !pos_profile.value?.company) {
		giftCardError.value = __("Gift card code is required.");
		return;
	}

	if (isOffline()) {
		const cached = getCachedGiftCardSnapshot(giftCardCode.value);
		if (!cached) {
			giftCardError.value = __("No cached gift card balance is available offline.");
			return;
		}
		giftCardBalance.value = flt(cached.current_balance || 0, currency_precision.value);
		giftCardStatus.value = cached.status || "";
		return;
	}

	giftCardLoading.value = true;
	giftCardError.value = "";
	try {
		const response = await frappe.call({
			method: "posawesome.posawesome.api.gift_cards.check_gift_card_balance",
			args: {
				gift_card_code: giftCardCode.value,
				company: pos_profile.value.company,
			},
		});
		const card = response?.message || {};
		giftCardBalance.value = flt(card.current_balance || 0, currency_precision.value);
		giftCardStatus.value = card.status || "";
		saveGiftCardSnapshot(giftCardCode.value, card);
		if (!giftCardAmount.value && giftCardMode.value === "redeem") {
			giftCardAmount.value = Math.min(giftCardBalance.value, getGiftCardRemainingAmount());
		}
	} catch (error) {
		giftCardError.value = error?.message || __("Unable to load gift card balance.");
	}
	giftCardLoading.value = false;
};

const applyGiftCardRedemption = async () => {
	if (!giftCardBalance.value || !giftCardStatus.value) {
		await checkGiftCardBalance();
		if (!giftCardBalance.value || giftCardError.value) {
			return;
		}
	}

	const nextAmount = Math.min(
		flt(giftCardAmount.value || 0, currency_precision.value),
		giftCardBalance.value,
		getGiftCardRemainingAmount(),
	);

	if (nextAmount <= 0) {
		giftCardError.value = __("Gift card amount must be greater than zero.");
		return;
	}

	if (activeGiftCardPayment.value) {
		activeGiftCardPayment.value.amount = 0;
		if (activeGiftCardPayment.value.base_amount !== undefined) {
			activeGiftCardPayment.value.base_amount = 0;
		}
	}
	giftCardRedemptions.value = [
		{
			gift_card_code: giftCardCode.value,
			amount: nextAmount,
			cashier: currentCashier.value?.user || null,
		},
	];
	rebalancePreferredPaymentCoverage(nextAmount);
	giftCardInlineExpanded.value = false;
	giftCardDialogOpen.value = false;
};

const issueGiftCard = async () => {
	if (!currentCashier.value?.is_supervisor) {
		giftCardError.value = __("A POS supervisor is required for this action.");
		return;
	}
	giftCardLoading.value = true;
	giftCardError.value = "";
	try {
		const response = await frappe.call({
			method: "posawesome.posawesome.api.gift_cards.issue_gift_card",
			args: {
				pos_profile: pos_profile.value?.name,
				cashier: currentCashier.value?.user,
				company: pos_profile.value?.company,
				initial_amount: flt(giftCardAmount.value || 0, currency_precision.value),
				gift_card_code: giftCardCode.value || null,
				currency: invoice_doc.value?.currency || pos_profile.value?.currency,
			},
		});
		const card = response?.message || {};
		giftCardCode.value = card.gift_card_code || giftCardCode.value;
		giftCardBalance.value = flt(card.current_balance || 0, currency_precision.value);
		giftCardStatus.value = card.status || "Active";
		giftCardMode.value = "redeem";
	} catch (error) {
		giftCardError.value = error?.message || __("Unable to issue gift card.");
	}
	giftCardLoading.value = false;
};

const topUpGiftCard = async () => {
	if (!currentCashier.value?.is_supervisor) {
		giftCardError.value = __("A POS supervisor is required for this action.");
		return;
	}
	giftCardLoading.value = true;
	giftCardError.value = "";
	try {
		const response = await frappe.call({
			method: "posawesome.posawesome.api.gift_cards.top_up_gift_card",
			args: {
				pos_profile: pos_profile.value?.name,
				cashier: currentCashier.value?.user,
				gift_card_code: giftCardCode.value,
				amount: flt(giftCardAmount.value || 0, currency_precision.value),
			},
		});
		const card = response?.message || {};
		giftCardBalance.value = flt(card.current_balance || 0, currency_precision.value);
		giftCardStatus.value = card.status || "Active";
		giftCardMode.value = "redeem";
	} catch (error) {
		giftCardError.value = error?.message || __("Unable to top up gift card.");
	}
	giftCardLoading.value = false;
};

// Methods

const get_print_formats = async () => {
	const doctypes = resolvePaymentPrintFormatDoctypes({
		profile: pos_profile.value,
		invoiceType: invoiceType.value,
	});

	try {
		const responses = await Promise.all(
			doctypes.map((doctype) =>
				frappe.call({
					method: "posawesome.posawesome.api.print_formats.get_print_formats",
					args: { doctype },
				}),
			),
		);

		const mergedFormats = responses
			.flatMap((response) => response?.message || [])
			.map((pf) => (typeof pf === "object" && pf.name ? pf.name : pf))
			.filter(Boolean);

		print_formats.value = Array.from(new Set(mergedFormats));
		set_print_format();
	} catch (error) {
		console.error("Failed to fetch payment print formats", error);
		print_formats.value = [];
		set_print_format();
	}
};

const set_print_format = () => {
	print_format.value = resolvePaymentPrintFormat({
		profile: pos_profile.value,
		customerInfo: customer_info.value,
		availableFormats: print_formats.value,
	});
};

const releaseActiveFocus = () => {
	if (typeof document === "undefined") {
		return;
	}
	const active = document.activeElement;
	if (active instanceof HTMLElement && active !== document.body) {
		active.blur();
	}
};

const triggerSearchFocusRecovery = () => {
	nextTick(() => {
		uiStore.triggerItemSearchFocus();
		if (eventBus && typeof eventBus.emit === "function") {
			eventBus.emit("focus_item_search");
		}
	});
};

const queueSearchRefocusRecovery = () => {
	if (typeof window === "undefined") {
		triggerSearchFocusRecovery();
		return;
	}

	let fallbackTimer = null;
	let cleanupTimer = null;
	const recover = () => {
		triggerSearchFocusRecovery();
	};

	const cleanup = () => {
		window.removeEventListener("focus", onWindowFocus);
		if (fallbackTimer) {
			clearTimeout(fallbackTimer);
			fallbackTimer = null;
		}
		if (cleanupTimer) {
			clearTimeout(cleanupTimer);
			cleanupTimer = null;
		}
	};

	const onWindowFocus = () => {
		recover();
		cleanup();
	};

	window.addEventListener("focus", onWindowFocus);
	if (fallbackTimer) {
		clearTimeout(fallbackTimer);
		fallbackTimer = null;
	}
	fallbackTimer = setTimeout(() => {
		recover();
		cleanup();
	}, 900);
	if (cleanupTimer) {
		clearTimeout(cleanupTimer);
		cleanupTimer = null;
	}
	cleanupTimer = setTimeout(() => {
		cleanup();
	}, 10000);
};

const back_to_invoice = () => {
	releaseActiveFocus();
	paymentVisible.value = false;
	missingOrderAddressDialog.value = false;
	pendingMissingAddressSubmit.value = null;
	if (paymentDialogOpen.value) {
		uiStore.closePaymentDialog();
	}
	if (activeView.value === "payment") {
		uiStore.setActiveView("items");
	}
	queueSearchRefocusRecovery();
};

const finishSubmissionNavigation = (clearInvoice = false) => {
	const submittedType = invoiceType.value;
	back_to_invoice();
	if (clearInvoice) {
		addresses.value = [];
		invoiceStore.clear();
		invoiceStore.resetPostingDate();
		if (eventBus && typeof eventBus.emit === "function") {
			eventBus.emit("clear_invoice");
		}

		if (submittedType !== "Invoice") {
			invoiceType.value = "Invoice";
			if (eventBus && typeof eventBus.emit === "function") {
				eventBus.emit("reset_invoice_type_to_invoice");
			}
		}
	}
};

const buildProfilePaymentLines = () => {
	const profilePayments = Array.isArray(pos_profile.value?.payments) ? pos_profile.value.payments : [];

	return profilePayments
		.filter((payment) => payment?.mode_of_payment)
		.map((payment, index) => ({
			mode_of_payment: payment.mode_of_payment,
			amount: 0,
			base_amount: 0,
			account: payment.account,
			type: payment.type,
			default: payment.default === 1 || payment.default === true || index === 0 ? 1 : 0,
		}));
};

const syncPreferredPaymentToCurrentTotal = (doc = invoice_doc.value) => {
	if (!doc || !Array.isArray(doc.payments) || !doc.payments.length || is_credit_sale.value) {
		return null;
	}

	const payments = doc.payments.filter((payment) => payment?.mode_of_payment);
	if (!payments.length) {
		return null;
	}

	const preferredPayment = resolvePreferredPaymentLine(doc, isCashLikePayment);
	if (!preferredPayment) {
		return null;
	}

	const otherMeaningfulPayments = payments.filter((payment) => {
		if (payment === preferredPayment) {
			return false;
		}
		return Math.abs(flt(payment.amount || 0, currency_precision.value)) > 0.0001;
	});

	if (otherMeaningfulPayments.length) {
		return preferredPayment;
	}

	const total = netInvoiceSettlementAmount.value;
	const normalizedTotal = doc.is_return ? -Math.abs(total) : Math.abs(total);
	const conversionRate = flt(doc.conversion_rate || 1, currency_precision.value);

	payments.forEach((payment) => {
		if (payment !== preferredPayment) {
			payment.amount = 0;
			if (payment.base_amount !== undefined) {
				payment.base_amount = 0;
			}
		}
	});

	preferredPayment.amount = normalizedTotal;
	if (preferredPayment.base_amount !== undefined) {
		preferredPayment.base_amount = flt(normalizedTotal * conversionRate, currency_precision.value);
	}

	return preferredPayment;
};

const rebalancePreferredPaymentCoverage = (giftCardAmount = giftCardAppliedAmount.value) => {
	const doc = invoice_doc.value;
	if (
		!doc ||
		doc.is_return ||
		is_credit_sale.value ||
		!Array.isArray(doc.payments) ||
		!doc.payments.length
	) {
		return null;
	}

	return rebalancePreferredPaymentLine(doc, {
		precision: currency_precision.value,
		isCashLikePayment,
		loyaltyAmount: invoice_doc.value?.loyalty_amount || loyalty_amount.value,
		redeemedCustomerCredit: redeemed_customer_credit.value,
		giftCardAmount,
	});
};

const mergeProfilePaymentsIntoReturn = (doc) => {
	const profilePayments = buildProfilePaymentLines();
	if (!profilePayments.length) return;

	if (!Array.isArray(doc.payments)) {
		doc.payments = [];
	}

	const existingModes = new Set(doc.payments.map((p) => p?.mode_of_payment).filter(Boolean));

	profilePayments.forEach((pp) => {
		if (!existingModes.has(pp.mode_of_payment)) {
			doc.payments.push({
				mode_of_payment: pp.mode_of_payment,
				amount: 0,
				base_amount: 0,
				default: pp.default,
				account: pp.account,
				type: pp.type,
			});
		}
	});
};

const ensurePaymentLinesInitialized = (doc = invoice_doc.value) => {
	if (!doc) {
		return null;
	}

	if (!Array.isArray(doc.payments) || !doc.payments.length) {
		const fallbackPayments = buildProfilePaymentLines();
		if (fallbackPayments.length) {
			doc.payments = fallbackPayments;
		}
	}

	// For returns, always show all profile payment methods so user can split refund
	if (doc.is_return) {
		mergeProfilePaymentsIntoReturn(doc);
	}

	const initializedPayment = initializePaymentLinesForDialog(
		doc,
		currency_precision.value,
		isCashLikePayment,
	);

	if (doc.is_return) {
		ensureReturnPaymentsAreNegative();
	}

	syncPreferredPaymentToCurrentTotal(doc);

	return initializedPayment;
};

const restorePaymentLinesAfterFailedSubmit = () => {
	const doc = invoice_doc.value;
	if (!doc) {
		return;
	}

	ensurePaymentLinesInitialized(doc);
	is_credit_sale.value = false;
};

const handleShowPayment = () => {
	paymentVisible.value = true;
	nextTick(() => {
		setTimeout(() => {
			const btn = submitButton.value;
			const el = btn && btn.$el ? btn.$el : btn;
			if (el) {
				el.scrollIntoView({ behavior: "smooth", block: "center" });
				el.focus();
				highlightSubmit.value = true;
			}
			if (eventBus && typeof eventBus.emit === "function") {
				eventBus.emit("payment_ui_ready");
			}
			if (queuedShortcutSubmit.value) {
				const payload = queuedShortcutSubmit.value;
				queuedShortcutSubmit.value = null;
				handleSubmitPaymentShortcut(payload || {});
			}
		}, 100);
	});
};

const handleCreditChangeUpdate = (value) => {
	setFormatedCurrency(credit_change, "value", null, false, value);
	updateCreditChange(credit_change.value);
};

const handleWriteOffAmountUpdate = (value) => {
	if (!invoice_doc.value) return;

	let nextAmount = flt(value || 0, currency_precision.value);
	const profileCap = writeOffProfileLimit.value;
	const diffCap = Math.max(diff_payment.value || 0, 0);
	const maxAmount = profileCap && profileCap > 0 ? Math.min(diffCap, profileCap) : diffCap;

	if (nextAmount < 0) {
		nextAmount = 0;
	}
	if (profileCap && profileCap > 0 && nextAmount > profileCap) {
		toastStore.show({
			title: __("Write off amount cannot exceed the POS profile maximum of {0}", [
				formatCurrency(profileCap),
			]),
			color: "error",
		});
		nextAmount = maxAmount;
	}
	if (nextAmount > maxAmount) {
		nextAmount = maxAmount;
	}

	invoice_doc.value.write_off_amount = nextAmount;
};

const handleRedemptionFormattedCurrency = (data) => {
	if (!data?.field) return;

	if (data.field === "loyalty_amount") {
		setFormatedCurrency(loyalty_amount, "value", null, false, data.value);
		return;
	}

	if (data.field === "redeemed_customer_credit") {
		setFormatedCurrency(redeemed_customer_credit, "value", null, false, data.value);
	}
};

const updateCreditChange = (rawValue) => {
	const changeLimit = Math.max(-diff_payment.value, 0);
	let requestedCredit = flt(Math.abs(rawValue) || 0, currency_precision.value);

	if (requestedCredit > changeLimit) {
		requestedCredit = changeLimit;
	}

	const remainingPaidChange = flt(changeLimit - requestedCredit, currency_precision.value);

	credit_change.value = requestedCredit;
	paid_change.value = remainingPaidChange;

	if (invoice_doc.value) {
		invoice_doc.value.credit_change = requestedCredit;
		invoice_doc.value.paid_change = remainingPaidChange;
	}
};

const handlePaymentAmountChange = (payment, event) => {
	last_payment_change_was_cash.value = isCashLikePayment(payment);
	setFormatedCurrency(payment, "amount", null, false, event);

	// For return invoices: user enters a positive number but we store it as negative (refund)
	if (invoice_doc.value?.is_return && payment.amount > 0) {
		payment.amount = -payment.amount;
	}
	if (payment.base_amount !== undefined && invoice_doc.value?.is_return) {
		const conversion_rate = invoice_doc.value.conversion_rate || 1;
		payment.base_amount = flt(payment.amount * conversion_rate, currency_precision.value);
	}

	nextTick(() => {
		autoBalancePayments(payment);
	});
};

const setPaymentToDenomination = (payment, amount) => {
	payment.amount = amount;
	if (payment.base_amount !== undefined) {
		const conversion_rate = invoice_doc.value.conversion_rate || 1;
		payment.base_amount = flt(amount * conversion_rate, currency_precision.value);
	}
	last_payment_change_was_cash.value = isCashLikePayment(payment);
	nextTick(() => {
		autoBalancePayments(payment);
	});
};

// UI Feedback Methods
const showPaidAmount = () => {
	toastStore.show({
		title: `Total Paid Amount: ${formatCurrency(total_payments.value)}`,
		color: "info",
	});
};

const creditSourceLabel = (row) => {
	if (!row) return "";
	const sourceLabel = row.source_type ? __(row.source_type) : null;
	if (sourceLabel) return `${sourceLabel}: ${row.credit_origin}`;
	return row.credit_origin;
};

const showDiffPayment = () => {
	if (!invoice_doc.value) return;
	toastStore.show({
		title: `To Be Paid: ${formatCurrency(
			diff_payment.value < 0 ? -diff_payment.value : diff_payment.value,
		)}`,
		color: "info",
	});
};

const showPaidChange = () => {
	toastStore.show({
		title: `Paid Change: ${formatCurrency(paid_change.value)}`,
		color: "info",
	});
};

// Background Check
const clearBackgroundStatusCheck = () => {
	if (backgroundStatusCheck.value) {
		clearTimeout(backgroundStatusCheck.value);
		backgroundStatusCheck.value = null;
	}
};

const resolveSubmittedDoctype = (doctype) => {
	if (doctype) return doctype;
	if (invoice_doc.value?.doctype) return invoice_doc.value.doctype;
	return pos_profile.value?.create_pos_invoice_instead_of_sales_invoice ? "POS Invoice" : "Sales Invoice";
};

const fetchSubmittedInvoiceDoc = async (invoiceName, doctype) => {
	const resolvedDoctype = resolveSubmittedDoctype(doctype);
	return frappe.db.get_doc(resolvedDoctype, invoiceName);
};

const waitForInvoiceSubmission = async (invoiceName, doctype) => {
	try {
		return await socketStore.waitForInvoiceProcessed(invoiceName, 45000);
	} catch (error) {
		const result = await frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: resolveSubmittedDoctype(doctype),
				filters: { name: invoiceName },
				fieldname: ["docstatus"],
			},
		});
		if (result?.message?.docstatus === 1) {
			return {
				status: "processed",
				doctype: resolveSubmittedDoctype(doctype),
			};
		}
		throw error;
	}
};

const runDeferredPrintWorkflow = async ({
	name,
	doctype,
	waitForPostSubmitPayments = false,
	waitForInvoiceProcessing = false,
}) => {
	if (!name) return;

	let resolvedDoctype = resolveSubmittedDoctype(doctype);

	try {
		if (waitForInvoiceProcessing) {
			const processedState = await waitForInvoiceSubmission(name, resolvedDoctype);
			resolvedDoctype = processedState?.doctype || resolvedDoctype;
		}

		if (waitForPostSubmitPayments) {
			await socketStore.waitForPostSubmitPayments(name, 45000);
		}

		const freshDoc = await fetchSubmittedInvoiceDoc(name, resolvedDoctype);

		if (isOffline()) {
			await printOfflineInvoice(freshDoc);
			return;
		}

		await loadPrintPage({ doc: freshDoc, doctype: resolvedDoctype });
	} catch (error) {
		console.error("Deferred print failed", error);
		toastStore.show({
			title: __("Unable to print submitted invoice"),
			color: "error",
			detail: error?.message || __("Background processing did not finish in time."),
		});
	}
};

const scheduleBackgroundStatusCheck = ({
	name,
	doctype,
	print = false,
	waitForPostSubmitPayments = false,
	waitForInvoiceProcessing = false,
} = {}) => {
	clearBackgroundStatusCheck();

	if (!name) {
		return;
	}

	if (print && (waitForInvoiceProcessing || waitForPostSubmitPayments)) {
		void runDeferredPrintWorkflow({
			name,
			doctype,
			waitForPostSubmitPayments,
			waitForInvoiceProcessing,
		});
	}

	if (waitForInvoiceProcessing) {
		return;
	}

	backgroundStatusCheck.value = setTimeout(async () => {
		try {
			const result = await frappe.call({
				method: "frappe.client.get_value",
				args: {
					doctype: resolveSubmittedDoctype(doctype),
					filters: { name },
					fieldname: ["docstatus"],
				},
			});
			const status = result?.message?.docstatus;
			if (status === 1) {
				return;
			}
			const reason = __("Invoice is still in draft after background submission.");
			if (eventBus && typeof eventBus.emit === "function") {
				eventBus.emit("invoice_submission_failed", {
					invoice: name,
					reason,
				});
			}
			toastStore.show({
				title: __("Error submitting invoice: {0}", [name]),
				color: "error",
				detail: reason,
			});
		} catch (err) {
			console.error("Background status check failed", err);
		} finally {
			clearBackgroundStatusCheck();
		}
	}, 10000);
};

// Submission Wrapper
const submit = async (_event, payment_received = false, print = false) => {
	if (isWizardFlow.value && currentStep.value === 1) {
		if (canProceedToPayment.value) {
			currentStep.value = 2;
		}
		return;
	}
	await submitInvoiceWrapper(print, undefined, {
		paymentReceived: payment_received,
	});
};

const submitWithoutPaymentOrder = async () => {
	if (isWizardFlow.value && currentStep.value === 1) {
		if (canProceedToPayment.value) {
			currentStep.value = 2;
		}
		return;
	}

	await submitInvoiceWrapper(false, undefined, {
		allowNoPaymentOrderSubmit: true,
		forceHoldOrder: true,
	});
};

const shouldConfirmMissingOrderAddress = (options = {}) => {
	if (options.skipMissingAddressConfirmation) {
		return false;
	}
	if (invoiceType.value !== "Order") {
		return false;
	}
	if (!pos_profile.value?.posa_create_only_sales_order) {
		return false;
	}
	const shippingAddress = invoice_doc.value?.shipping_address_name;
	return !String(shippingAddress || "").trim();
};

const isCollectionDeliveryChargeSelected = () => {
	const selectedName = String(
		invoice_doc.value?.posa_delivery_charges || selectedDeliveryCharge.value || "",
	).trim();
	if (!selectedName) {
		return false;
	}
	const selectedRow = (Array.isArray(deliveryCharges.value) ? deliveryCharges.value : []).find(
		(row) => String(row?.name || "").trim() === selectedName,
	);
	const collectionFlag = selectedRow?.collection;
	return collectionFlag === 1 || collectionFlag === "1" || collectionFlag === true;
};

const shouldUseCollectedAddressEntry = (options = {}) => {
	return shouldConfirmMissingOrderAddress(options) && isCollectionDeliveryChargeSelected();
};

const addressActionLabel = computed(() =>
	shouldUseStoreCollectionFlow.value
		? __("Select a store collection point below")
		: isCollectionDeliveryChargeSelected()
		? __("Add Customer Collection Information")
		: __("Add Customer Address"),
);

const shippingAddressLabel = computed(() =>
	shouldUseStoreCollectionFlow.value
		? __("Store Collection Point *")
		: __("Shipping Address *"),
);

const showAddressAction = computed(() => !shouldUseStoreCollectionFlow.value);

const showCollectionItemsValidationError = () => {
	frappe.msgprint({
		title: __("Collection Not Allowed"),
		message: __("Only NS items can be collected."),
		indicator: "red",
	});
};

const proceedFromFulfillmentStep = () => {
	fulfillmentValidationVisible.value = true;
	if (!hasOnlyNsItemsForCollection.value) {
		showCollectionItemsValidationError();
		return;
	}
	if (!canProceedToPayment.value) {
		return;
	}
	fulfillmentValidationVisible.value = false;
	currentStep.value = isSplitDeliveryEnabled.value ? 2 : 2;
};

const proceedToPaymentStep = () => {
	if (isSplitDeliveryEnabled.value && !canProceedFromGrouping.value) {
		return;
	}
	currentStep.value = 3;
};

const goToFulfillmentStep = () => {
	if (!isWizardFlow.value) {
		return;
	}
	currentStep.value = 1;
};

const goToPreviousWizardStep = () => {
	if (!isWizardFlow.value) {
		return;
	}
	if (isSplitDeliveryEnabled.value && currentStep.value === 3) {
		currentStep.value = 2;
		return;
	}
	currentStep.value = 1;
};

const createSplitGroup = (label) => {
	if (!invoice_doc.value) {
		return;
	}
	if (splitOrderGroups.value.length >= MAX_SPLIT_GROUPS) {
		frappe.msgprint({
			title: __("Limit Reached"),
			message: __("You can create a maximum of {0} groups.", [MAX_SPLIT_GROUPS]),
			indicator: "red",
		});
		return;
	}
	const nextIndex = splitOrderGroups.value.length + 1;
	invoice_doc.value.posa_split_groups = [
		...splitOrderGroups.value,
		{
			group_id: `group-${Date.now().toString(36)}-${nextIndex}`,
			label: __("Group {0}", [nextIndex]),
			row_ids: [],
		},
	];
};

const removeSplitGroup = (groupId) => {
	if (!invoice_doc.value || groupId === defaultSplitGroupId) {
		return;
	}
	const groups = splitOrderGroups.value.map((group) => ({ ...group, row_ids: [...(group.row_ids || [])] }));
	const target = groups.find((group) => group.group_id === groupId);
	const fallback = groups.find((group) => group.group_id === defaultSplitGroupId);
	if (!target || !fallback) {
		return;
	}
	fallback.row_ids.push(...(target.row_ids || []));
	invoice_doc.value.posa_split_groups = groups.filter((group) => group.group_id !== groupId);
};

const moveSplitGroupItem = ({ rowId, groupId }) => {
	if (!invoice_doc.value) {
		return;
	}
	const normalizedRowId = String(rowId || "").trim();
	const normalizedGroupId = String(groupId || "").trim();
	if (!normalizedRowId || !normalizedGroupId) {
		return;
	}
	const groups = splitOrderGroups.value.map((group) => ({
		...group,
		row_ids: (group.row_ids || []).filter((id) => id !== normalizedRowId),
	}));
	const target = groups.find((group) => group.group_id === normalizedGroupId);
	if (!target) {
		return;
	}
	target.row_ids.push(normalizedRowId);
	invoice_doc.value.posa_split_groups = groups;
};

const handlePaymentNewAddress = () => {
	if (shouldUseStoreCollectionFlow.value) {
		return;
	}

	const selectedAddressName = String(invoice_doc.value?.shipping_address_name || "").trim();
	const selectedAddress = (Array.isArray(addresses.value) ? addresses.value : []).find(
		(addr) => String(addr?.name || "").trim() === selectedAddressName,
	);

	if (isCollectionDeliveryChargeSelected()) {
		new_address({
			mode: "collected",
			address: selectedAddress || undefined,
		});
		return;
	}
	new_address({
		mode: "full",
		address: selectedAddress || undefined,
	});
};

const fetchStoreCollectionAddresses = async () => {
	try {
		const response = await frappe.call({
			method: "posawesome.posawesome.api.customers.get_store_collection_addresses",
		});
		storeCollectionAddresses.value = Array.isArray(response?.message)
			? response.message
					.map((row) => normalizeAddress(row))
					.filter((row) => row !== null)
			: [];
	} catch (error) {
		console.error("Failed to fetch store collection addresses", error);
		storeCollectionAddresses.value = [];
		toastStore.show({
			title: __("Unable to load store collection points"),
			color: "error",
		});
	}
};

const ensureStoreCollectionAddressLinked = async (addressName) => {
	const customer = String(invoice_doc.value?.customer || "").trim();
	const normalizedName = String(addressName || "").trim();
	if (!customer || !normalizedName) {
		return normalizedName || null;
	}

	const response = await frappe.call({
		method: "posawesome.posawesome.api.customers.link_store_collection_address_to_customer",
		args: {
			customer,
			address_name: normalizedName,
		},
	});

	return String(response?.message?.address_name || normalizedName).trim();
};

const handleShippingAddressSelection = async (addressName) => {
	if (!invoice_doc.value) {
		return;
	}

	const normalizedName = String(addressName || "").trim() || null;
	if (shouldUseStoreCollectionFlow.value && normalizedName) {
		selectedStoreCollectionAddressName.value = normalizedName;
		let linkedCopyName = normalizedName;
		try {
			linkedCopyName = await ensureStoreCollectionAddressLinked(normalizedName);
		} catch (error) {
			console.error("Failed to link store collection address to customer", error);
			toastStore.show({
				title: __("Unable to link store collection point to customer"),
				color: "error",
			});
			return;
		}
		invoice_doc.value.shipping_address_name = linkedCopyName;
		invoice_doc.value.customer_address = linkedCopyName;
		return;
	}
	selectedStoreCollectionAddressName.value = null;
	invoice_doc.value.shipping_address_name = normalizedName;
	invoice_doc.value.customer_address = normalizedName;
};

const confirmCustomerCollectedOrder = async () => {
	missingOrderAddressDialog.value = false;
	if (!pendingMissingAddressSubmit.value) {
		return;
	}
	pendingCollectedAddressSubmit.value = true;
	new_address({ mode: "collected" });
};

const openMissingOrderAddressEntry = () => {
	pendingMissingAddressSubmit.value = null;
	missingOrderAddressDialog.value = false;
	new_address();
};

const submitInvoiceWrapper = async (print, callbackOverrides = {}, options = {}) => {
	if (!hasOnlyNsItemsForCollection.value) {
		showCollectionItemsValidationError();
		return;
	}

	if (shouldUseCollectedAddressEntry(options)) {
		pendingMissingAddressSubmit.value = {
			print,
			callbackOverrides,
			options,
		};
		pendingCollectedAddressSubmit.value = true;
		new_address({ mode: "collected" });
		return;
	}

	if (shouldConfirmMissingOrderAddress(options)) {
		pendingMissingAddressSubmit.value = {
			print,
			callbackOverrides,
			options,
		};
		missingOrderAddressDialog.value = true;
		return;
	}

	if (submissionInFlight.value) {
		return;
	}

	const hasRequiredRevolutReference = await ensureRequiredRevolutReference();
	if (!hasRequiredRevolutReference) {
		return;
	}

	submissionInFlight.value = true;
	loading.value = true;
	const shouldHoldOrder = Boolean(options.forceHoldOrder || effectiveHoldOrder.value);
	const holdReason = options.forceHoldOrder
		? "submitted without payment"
		: autoHoldFromPreferredDelivery.value
			? "preferred delivery date is more than 2 weeks away"
			: isPartialPaymentOrder.value
				? "partial payment received"
				: String(invoice_doc.value?.posa_notes || "").trim();
	const holdReleaseDate = shouldHoldOrder
		? (
			options.forceHoldOrder
				? null
				: normalizeDateForBackend(autoHoldReleaseDate.value || hold_release_date.value)
		)
		: null;
	if (invoice_doc.value) {
		invoice_doc.value.posa_pending_auto_hold_reason = !shouldHoldOrder
			? ""
			: options.forceHoldOrder
				? "No Payment"
				: autoHoldFromPreferredDelivery.value
					? "Preferred Delivery Date"
					: isPartialPaymentOrder.value
						? "Partial Payment"
						: "Other";
	}
	try {
		await validateSubmission(options.paymentReceived || false, {
			allowNoPaymentOrderSubmit: Boolean(options.allowNoPaymentOrderSubmit),
		});
		await submitInvoice(print, {
			onPrint: (doc, printOptions = {}) => {
				if (print) {
					if (printOptions.waitForPostSubmitPayments || printOptions.waitForInvoiceProcessing) {
						void runDeferredPrintWorkflow({
							name: printOptions.name || doc?.name,
							doctype: printOptions.doctype,
							waitForPostSubmitPayments: Boolean(printOptions.waitForPostSubmitPayments),
							waitForInvoiceProcessing: Boolean(printOptions.waitForInvoiceProcessing),
						});
					} else if (isOffline()) {
						printOfflineInvoice(doc);
					} else {
						loadPrintPage({
							doc,
							doctype: printOptions.doctype,
						});
					}
				}
			},
			onSuccess: async (submittedDoc) => {
				const submittedDoctype =
					submittedDoc?.doctype ||
					(invoiceType.value === "Order" && pos_profile.value?.posa_create_only_sales_order
						? "Sales Order"
						: "");
				const submittedOrderNames = Array.isArray(submittedDoc?.names)
					? submittedDoc.names.filter(Boolean)
					: submittedDoc?.name
						? [submittedDoc.name]
						: [];
				if (
					shouldHoldOrder &&
					submittedDoctype === "Sales Order" &&
					submittedOrderNames.length
				) {
					for (const salesOrderName of submittedOrderNames) {
						try {
							await frappe.call({
								method: "customer_due_dates.kit_items.overrides.sales_order.hold_sales_order_from_pos",
								args: {
									sales_order_name: salesOrderName,
									reason: holdReason,
									auto_release_date: holdReleaseDate,
								},
							});
						} catch (error) {
							console.error("Failed to place submitted sales order on hold", error);
							toastStore.show({
								title: __("Sales Order {0} was submitted but could not be placed on hold", [
									salesOrderName,
								]),
								color: "warning",
							});
						}
					}
				}
				customer_credit_dict.value = [];
				redeem_customer_credit.value = false;
				is_cashback.value = true;
				show_change_dialog.value = true;
				is_credit_return.value = false;
			},
			onFinishNavigation: (clearInvoice) => {
				finishSubmissionNavigation(clearInvoice);
			},
			onScheduleBackgroundCheck: (payload) => {
				scheduleBackgroundStatusCheck(payload);
			},
			...callbackOverrides,
		}, {
			allowNoPaymentOrderSubmit: Boolean(options.allowNoPaymentOrderSubmit),
		});
	} catch (error) {
		console.error("Submission failed propagate:", error);
		restorePaymentLinesAfterFailedSubmit();

		if (error?.message) {
			toastStore.show({
				title: error.message,
				color: "error",
			});
			frappe.utils.play_sound("error");
		}
	} finally {
		loading.value = false;
		submissionInFlight.value = false;
	}
};

// Keyboard Shortcuts
const handlePaymentShortcut = (event) => {
	if (event.defaultPrevented || submissionInFlight.value || loading.value) return;
	if (event.repeat) return;
	if (!paymentVisible.value) return;

	const isAltOnly = event.altKey && !event.ctrlKey && !event.metaKey;
	const key = event.key.toLowerCase();

	if (isAltOnly && key === "p") {
		event.preventDefault();
		event.stopPropagation();
		submit(null, false, true);
		return;
	}

	if ((isAltOnly || event.ctrlKey || event.metaKey) && key === "x") {
		event.preventDefault();
		event.stopPropagation();
		submit(null, false, false);
	}
};

const handleSubmitPaymentShortcut = ({ print = false } = {}) => {
	if (!paymentVisible.value || submissionInFlight.value || loading.value) return;
	nextTick(() => {
		submit(null, false, print);
	});
};

const queueShortcutSubmit = (payload = {}) => {
	queuedShortcutSubmit.value = payload;
	if (isPaymentOpen.value) {
		nextTick(() => {
			setTimeout(() => {
				if (!queuedShortcutSubmit.value) {
					return;
				}
				const pendingPayload = queuedShortcutSubmit.value;
				queuedShortcutSubmit.value = null;
				handleSubmitPaymentShortcut(pendingPayload || {});
			}, 150);
		});
	}
};

// Watchers
watch(
	() => uiStore.posProfile,
	(p) => {
		if (p) {
			pos_profile.value = p;
			stock_settings.value = uiStore.stockSettings || {};
			get_mpesa_modes();
			get_print_formats();
			resetGiftCardState({ clearPayment: true });
		}
	},
	{ immediate: true },
);

watch(
	invoiceType,
	(data) => {
		get_print_formats();
	if (invoice_doc.value && data !== "Order") {
			invoice_doc.value.posa_delivery_date = null;
			invoice_doc.value.prefered_earliest_delivery_date = null;
			invoice_doc.value.preferred_earliest_delivery_date = null;
			invoice_doc.value.customer_order_ref = null;
			invoice_doc.value.posa_split_groups = [];
			invoice_doc.value.posa_notes = null;
			invoice_doc.value.driver_notes = null;
			invoice_doc.value.posa_authorization_code = null;
			invoice_doc.value.posa_split_delivery = 0;
			invoice_doc.value.shipping_address_name = null;
			selectedStoreCollectionAddressName.value = null;
			customer_unsure_delivery_date.value = true;
			hold_release_date.value = null;
		} else if (invoice_doc.value && data === "Order") {
			new_delivery_date.value = null;
			ensureOrderRef();
			syncSplitGroupsState();
			preferred_delivery_date.value =
				invoice_doc.value.prefered_earliest_delivery_date ||
				invoice_doc.value.preferred_earliest_delivery_date ||
				null;
			invoice_doc.value.posa_delivery_date = null;
			invoice_doc.value.posa_split_delivery =
				invoice_doc.value.posa_split_delivery ? 1 : 0;
			applyDefaultPreferredDeliveryDate();
		}
		if (invoice_doc.value && data === "Return") {
			invoice_doc.value.is_return = 1;
			ensureReturnPaymentsAreNegative();
			is_return.value = true;
			is_credit_return.value = false;
			return_valid_upto_date.value = null;
		} else if (invoice_doc.value) {
			invoice_doc.value.is_return = 0;
			is_return.value = false;
			is_credit_return.value = false;
			return_valid_upto_date.value = null;
			restoreReturnPayments();
		}
	},
	{ immediate: true },
);

watch(canProceedToPayment, (ready) => {
	if (!ready && isWizardFlow.value && currentStep.value === 2 && !isSplitDeliveryEnabled.value) {
		currentStep.value = 1;
	}
});

watch(
	() => currentStep.value,
	(step) => {
		if (step !== 1) {
			fulfillmentValidationVisible.value = false;
		}
	},
);

watch(
	isWizardFlow,
	(enabled) => {
		currentStep.value = enabled ? 1 : 2;
	},
	{ immediate: true },
);

watch(
	() => invoice_doc.value?.posa_split_delivery,
	() => {
		syncSplitGroupsState();
		if (!isSplitDeliveryEnabled.value && currentStep.value > 2) {
			currentStep.value = 2;
		}
	},
	{ immediate: true },
);

watch(
	() => (invoice_doc.value?.items || []).map((item) => item?.posa_row_id || "").join("|"),
	() => {
		syncSplitGroupsState();
	},
	{ immediate: true },
);

watch(diff_payment, (newVal) => {
	if (is_user_editing_paid_change.value) return;

	const lastEditWasCash = last_payment_change_was_cash.value;

	if (newVal < 0) {
		const changeDue = -newVal;
		if (lastEditWasCash === false) {
			paid_change.value = flt(changeDue, currency_precision.value);
			credit_change.value = 0;
		} else {
			paid_change.value = changeDue;
		}
	} else {
		updateCreditChange(0);
	}

	last_payment_change_was_cash.value = null;
});

watch(paid_change, (newVal) => {
	const changeLimit = Math.max(-diff_payment.value, 0);
	if (newVal > changeLimit) {
		paid_change.value = changeLimit;
		credit_change.value = 0;
		paid_change_rules.value = ["Paid change can not be greater than total change!"];
	} else {
		paid_change_rules.value = [];
		credit_change.value = flt(changeLimit - newVal, currency_precision.value);
	}

	const effectivePaid = Math.min(paid_change.value, changeLimit);
	const creditAmount = flt(changeLimit - effectivePaid, currency_precision.value);

	if (invoice_doc.value) {
		invoice_doc.value.paid_change = effectivePaid;
		invoice_doc.value.credit_change = creditAmount > 0 ? creditAmount : 0;
	}
});

watch(loyalty_amount, (value) => {
	if (!invoice_doc.value) return;
	const amount = parseFloat(value) || 0;
	if (amount > available_points_amount.value + 0.001) {
		invoice_doc.value.loyalty_amount = 0;
		invoice_doc.value.redeem_loyalty_points = 0;
		invoice_doc.value.loyalty_points = 0;
		loyalty_amount.value = 0;
		toastStore.show({
			title: `Loyalty Amount can not be more than ${available_points_amount.value}`,
			color: "error",
		});
	} else {
		invoice_doc.value.loyalty_amount = flt(loyalty_amount.value);
		invoice_doc.value.redeem_loyalty_points = 1;

		let baseAmount = amount;
		const docCurrency = invoice_doc.value.currency;
		const baseCurrency = pos_profile.value.currency;

		if (docCurrency && baseCurrency && docCurrency !== baseCurrency) {
			baseAmount = amount * (invoice_doc.value.conversion_rate || 1);
		}

		invoice_doc.value.loyalty_points = parseInt(
			baseAmount / (customer_info.value.conversion_factor || 1),
		);

		rebalancePreferredPaymentCoverage();
	}
});

watch(redeemed_customer_credit, () => {
	rebalancePreferredPaymentCoverage();
});

watch(is_credit_sale, (newVal) => {
	if (!invoice_doc.value || !Array.isArray(invoice_doc.value.payments)) return;

	const doc = invoice_doc.value;
	const conversionRate = doc.conversion_rate || 1;

	// Always clear all payment methods first to prevent stale paid amounts.
	doc.payments.forEach((payment) => {
		payment.amount = 0;
		if (payment.base_amount !== undefined) {
			payment.base_amount = 0;
		}
	});

	if (!newVal && doc.payments.length) {
		const amount = flt(doc.rounded_total || doc.grand_total, currency_precision.value);
		const defaultPayment =
			doc.payments.find((payment) => payment.default === 1) ||
			doc.payments.find((payment) => isCashLikePayment(payment)) ||
			doc.payments[0];

		if (defaultPayment) {
			defaultPayment.amount = amount;
			if (defaultPayment.base_amount !== undefined) {
				defaultPayment.base_amount = flt(amount * conversionRate, currency_precision.value);
			}
		}
	}
});

watch(is_credit_return, (newVal) => {
	if (!invoice_doc.value) return;
	if (newVal) {
		is_cashback.value = false;
		invoice_doc.value.payments.forEach((payment) => {
			payment.amount = 0;
			if (payment.base_amount !== undefined) {
				payment.base_amount = 0;
			}
		});
	} else {
		is_cashback.value = true;
		ensureReturnPaymentsAreNegative();
	}
});

watch(
	() => invoice_doc.value.customer,
	(customer, previous) => {
		if (customer && invoiceType.value === "Order") {
			ensureOrderRef();
		}
		if (customer && customer !== previous) {
			if (shouldUseStoreCollectionFlow.value) {
				void fetchStoreCollectionAddresses();
			} else {
				get_addresses();
			}
			set_print_format();
		} else if (!customer) {
			addresses.value = [];
			storeCollectionAddresses.value = [];
			selectedStoreCollectionAddressName.value = null;
			set_print_format();
		}
	},
);

watch(isPaymentOpen, (isOpen) => {
	if (isOpen) {
		ensureOrderRef();
		ensurePaymentLinesInitialized();
		handleShowPayment();
	} else {
		releaseActiveFocus();
		paymentVisible.value = false;
		highlightSubmit.value = false;
		queuedShortcutSubmit.value = null;
		giftCardDialogOpen.value = false;
	}
});

watch(
	() => invoice_doc.value.posa_delivery_date,
	(date) => {
		if (!date) {
			if (invoice_doc.value) {
				invoice_doc.value.shipping_address_name = null;
			}
			selectedStoreCollectionAddressName.value = null;
			addresses.value = [];
			storeCollectionAddresses.value = [];
			return;
		}
		if (invoice_doc.value && invoice_doc.value.customer) {
			if (shouldUseStoreCollectionFlow.value) {
				void fetchStoreCollectionAddresses();
			} else {
				get_addresses();
			}
		}
	},
);

watch(
	() => invoice_doc.value,
	() => {
		applyDefaultPreferredDeliveryDate();
	},
	{ immediate: true },
);

watch(
	showFulfillmentStep,
	(visible) => {
		if (!visible) {
			return;
		}
		nextTick(() => {
			applyDefaultPreferredDeliveryDate();
		});
	},
	{ immediate: true },
);

watch(
	() =>
		invoice_doc.value.prefered_earliest_delivery_date ||
		invoice_doc.value.preferred_earliest_delivery_date,
	(date) => {
		preferred_delivery_date.value = date || null;
		if (date) {
			customer_unsure_delivery_date.value = false;
		}
	},
	{ immediate: true },
);

watch(
	() => invoice_doc.value?.collection_date,
	(date) => {
		collection_date.value = date || null;
	},
	{ immediate: true },
);

watch(
	showCollectionDate,
	(enabled) => {
		if (enabled) {
			return;
		}
		collection_date.value = null;
		if (invoice_doc.value) {
			invoice_doc.value.collection_date = null;
		}
	},
	{ immediate: true },
);

watch(
	preferredDeliveryDateEnabled,
	(enabled) => {
		if (enabled) {
			applyDefaultPreferredDeliveryDate();
			return;
		}
		if (!invoice_doc.value) {
			return;
		}
		preferred_delivery_date.value = null;
		invoice_doc.value.prefered_earliest_delivery_date = null;
		invoice_doc.value.preferred_earliest_delivery_date = null;
	},
	{ immediate: true },
);

watch(
	() => selectedDeliveryCharge.value,
	() => {
		if (!invoice_doc.value) {
			return;
		}

		invoice_doc.value.shipping_address_name = null;
		invoice_doc.value.customer_address = null;
		selectedStoreCollectionAddressName.value = null;

		if (!invoice_doc.value.customer) {
			addresses.value = [];
			storeCollectionAddresses.value = [];
			return;
		}

		if (shouldUseStoreCollectionFlow.value) {
			void fetchStoreCollectionAddresses();
			return;
		}

		storeCollectionAddresses.value = [];
		get_addresses();
	},
);

watch(
	showDeliverySchedulingFields,
	(enabled) => {
		if (enabled) {
			applyDefaultPreferredDeliveryDate();
			return;
		}
		if (!invoice_doc.value) {
			return;
		}

		preferred_delivery_date.value = null;
		customer_unsure_delivery_date.value = true;
		invoice_doc.value.posa_split_delivery = 0;
		invoice_doc.value.prefered_earliest_delivery_date = null;
		invoice_doc.value.preferred_earliest_delivery_date = null;
	},
	{ immediate: true },
);

watch(customerInfo, (newInfo) => {
	customer_info.value = newInfo || "";
	set_print_format();
});

watch(selectedCustomer, (newCustomer, oldCustomer) => {
	if (newCustomer === oldCustomer) return;
	customer_credit_dict.value = [];
	redeem_customer_credit.value = false;
	is_cashback.value = true;
	is_credit_return.value = false;
	loyalty_amount.value = 0;
	resetGiftCardState({ clearPayment: true });

	if (invoice_doc.value) {
		invoice_doc.value.loyalty_amount = 0;
		invoice_doc.value.redeem_loyalty_points = 0;
		invoice_doc.value.loyalty_points = 0;
	}
});

// Lifecycle
onMounted(() => {
	_shortcutHandlers.value.handlePaymentShortcut = handlePaymentShortcut.bind(this);
	document.addEventListener("keydown", _shortcutHandlers.value.handlePaymentShortcut);

	syncStore.syncPendingInvoices();
	eventBus.on("network-online", () => syncStore.syncPendingInvoices());
	eventBus.on("server-online", () => syncStore.syncPendingInvoices());

	if (eventBus) {
		eventBus.on("send_invoice_doc_payment", (doc) => {
			currentStep.value = isWizardFlow.value ? 1 : 2;
			invoiceStore.setInvoiceDoc(doc);
			const incomingDeliveryDate = String(
				doc?.prefered_earliest_delivery_date || doc?.preferred_earliest_delivery_date || "",
			).trim();
			if (incomingDeliveryDate) {
				customer_unsure_delivery_date.value = false;
			} else {
				customer_unsure_delivery_date.value = true;
				preferred_delivery_date.value = null;
			}
			applyDefaultPreferredDeliveryDate();
			paid_change.value = flt(doc.paid_change || 0, currency_precision.value);
			credit_change.value = flt(doc.credit_change || 0, currency_precision.value);
			last_payment_change_was_cash.value = null;
			is_credit_sale.value = false;
			is_write_off_change.value = false;

			const initializedPayment = ensurePaymentLinesInitialized(doc);

			if (doc.is_return) {
				is_return.value = true;
				is_credit_return.value = false;
			} else if (initializedPayment) {
				is_credit_return.value = false;
			}
			initializeReturnValidity(doc);
			loyalty_amount.value = 0;
			redeemed_customer_credit.value = 0;
			resetGiftCardState({ clearPayment: true });
			if (doc.customer) {
				if (shouldUseStoreCollectionFlow.value) {
					void fetchStoreCollectionAddresses();
				} else {
					get_addresses();
				}
			}
		});

		eventBus.on("register_pos_profile", (data) => {
			pos_profile.value = data.pos_profile;
			stock_settings.value = data.stock_settings;
		});
		eventBus.on("add_the_new_address", (data) => {
			const normalized = normalizeAddress(data);
			if (normalized) {
				const existing = addresses.value.filter((addr) => addr.name !== normalized.name);
				addresses.value = [...existing, normalized];
				if (invoice_doc.value) {
					invoice_doc.value.shipping_address_name = normalized.name;
					invoice_doc.value.customer_address = normalized.name;
				}
				if (pendingCollectedAddressSubmit.value && pendingMissingAddressSubmit.value) {
					const pendingSubmit = pendingMissingAddressSubmit.value;
					pendingCollectedAddressSubmit.value = false;
					pendingMissingAddressSubmit.value = null;
					void submitInvoiceWrapper(pendingSubmit.print, pendingSubmit.callbackOverrides, {
						...pendingSubmit.options,
						skipMissingAddressConfirmation: true,
					});
				}
			}
		});
		eventBus.on("set_pos_settings", (data) => {
			pos_settings.value = data || {};
			if (invoice_doc.value && !invoice_doc.value.is_return) {
				initializeReturnValidity(invoice_doc.value);
			}
		});
		eventBus.on("set_mpesa_payment", (data) => {
			set_mpesa_payment(data);
		});
		eventBus.on("queue_submit_payment_shortcut", queueShortcutSubmit);
		eventBus.on("submit_payment_shortcut", handleSubmitPaymentShortcut);
		eventBus.on("clear_invoice", () => {
			currentStep.value = isWizardFlow.value ? 1 : 2;
			invoiceStore.clear();
			invoiceStore.resetPostingDate();
			missingOrderAddressDialog.value = false;
			pendingMissingAddressSubmit.value = null;
			pendingCollectedAddressSubmit.value = false;
			storeCollectionAddresses.value = [];
			selectedStoreCollectionAddressName.value = null;
			customer_unsure_delivery_date.value = true;
			hold_release_date.value = null;
			is_return.value = false;
			is_credit_return.value = false;
			return_valid_upto_date.value = null;
			resetGiftCardState({ clearPayment: true });
		});
	}

	if (isPaymentOpen.value) {
		handleShowPayment("true");
	}
});

onBeforeUnmount(() => {
	currentStep.value = 1;
	missingOrderAddressDialog.value = false;
	pendingMissingAddressSubmit.value = null;
	pendingCollectedAddressSubmit.value = false;
	eventBus.off("send_invoice_doc_payment");
	eventBus.off("register_pos_profile");
	eventBus.off("add_the_new_address");
	eventBus.off("set_pos_settings");
	eventBus.off("set_mpesa_payment");
	eventBus.off("queue_submit_payment_shortcut", queueShortcutSubmit);
	eventBus.off("submit_payment_shortcut", handleSubmitPaymentShortcut);
	eventBus.off("clear_invoice");
	eventBus.off("network-online");
	eventBus.off("server-online");
	clearBackgroundStatusCheck();

	if (_shortcutHandlers.value.handlePaymentShortcut) {
		document.removeEventListener("keydown", _shortcutHandlers.value.handlePaymentShortcut);
	}
});
</script>

<style scoped>
/* Remove readonly styling */
.v-text-field--readonly {
	cursor: text;
}

.v-text-field--readonly:hover {
	background-color: transparent;
}

.cards {
	background-color: var(--pos-surface-muted) !important;
}

.payment-shell {
	padding: 0;
}

.payment-shell--dialog {
	height: calc(100dvh - 48px);
	display: flex;
	flex-direction: column;
	gap: var(--pos-space-2);
}

.payment-card {
	padding: var(--pos-space-2);
}

.payment-card--dialog {
	flex: 1 1 auto;
	min-height: 0;
	height: auto;
	max-height: none;
	margin-top: 0;
	display: flex;
	flex-direction: column;
}

.payment-scroll {
	padding: var(--pos-space-3);
	display: flex;
	flex-direction: column;
	gap: var(--pos-space-3);
	flex: 1 1 auto;
	min-height: 0;
}

.payment-sections {
	display: flex;
	flex-direction: column;
	gap: var(--pos-space-3);
}

.payment-wizard-header {
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 4px 2px 0;
}

.payment-wizard-header__title {
	font-size: 0.92rem;
	font-weight: 700;
	color: var(--pos-text-primary);
}

.payment-wizard-header__track {
	display: inline-flex;
	align-items: center;
	gap: 8px;
}

.payment-wizard-header__dot {
	width: 10px;
	height: 10px;
	border-radius: 999px;
	background: var(--pos-border-light);
	transition: background-color 0.15s ease;
}

.payment-wizard-header__dot--active {
	background: rgb(var(--v-theme-primary));
}

.payment-sections--dialog {
	display: grid;
	grid-template-columns: minmax(0, 1.05fr) minmax(0, 0.95fr);
	gap: var(--pos-space-2);
	align-items: start;
	grid-template-areas:
		"summary adjustments"
		"methods adjustments"
		"settlement adjustments"
		"settlement meta";
}

.payment-sections--wizard-step1 {
	display: flex;
	width: 100%;
	grid-template-columns: none;
	grid-template-areas: none;
}

.payment-sections--wizard-step1 .payment-section {
	width: 100%;
	max-width: none;
}

.payment-section {
	background: var(--pos-surface-muted);
	border: 1px solid var(--pos-border-light);
	border-radius: var(--pos-radius-md);
	padding: var(--pos-space-3);
	display: flex;
	flex-direction: column;
	gap: var(--pos-space-3);
}

.payment-sections--dialog .payment-section {
	padding: 10px;
	gap: 10px;
}

.payment-sections--dialog .payment-section--summary {
	grid-area: summary;
}

.payment-sections--dialog .payment-section--methods {
	grid-area: methods;
}

.payment-sections--dialog .payment-section--settlement {
	grid-area: settlement;
}

.payment-sections--dialog .payment-section--adjustments {
	grid-area: adjustments;
}

.payment-sections--dialog .payment-section--grouping {
	grid-column: 1 / -1;
}

.payment-sections--dialog .payment-section--meta {
	grid-area: meta;
}

.payment-section--summary {
	background: linear-gradient(180deg, rgba(var(--v-theme-primary), 0.08) 0%, var(--pos-surface-muted) 100%);
}

.payment-section__header {
	display: flex;
	flex-direction: column;
	gap: 0;
}

.payment-section__subsection {
	display: flex;
	flex-direction: column;
	gap: 2px;
	padding-top: var(--pos-space-1);
	border-top: 1px solid var(--pos-border-light);
}

.payment-section__title {
	margin: 0;
	font-size: 1rem;
	font-weight: 700;
	line-height: 1.2;
	color: var(--pos-text-primary);
}

.payment-section__title--subsection {
	font-size: 0.92rem;
}

:deep(.payment-section .v-divider) {
	display: none;
}

:deep(.payment-section .v-field) {
	border-radius: var(--pos-radius-sm);
}

.payment-footer {
	flex: 0 0 auto;
	position: sticky;
	bottom: 0;
	z-index: 8;
	padding-top: 8px;
	background: linear-gradient(180deg, rgba(255, 255, 255, 0), var(--pos-surface) 30%);
}

.payment-wizard-actions {
	display: flex;
	justify-content: flex-start;
	padding: 0 4px 8px;
}

.payment-next-step {
	display: flex;
	justify-content: space-between;
	align-items: center;
	padding-top: 4px;
}

.payment-footer--dialog {
	margin-top: 0;
}

:deep(.payment-footer--dialog .cards) {
	margin-top: 0 !important;
}

:deep(.payment-footer--dialog .v-btn) {
	min-height: 42px;
}

:deep(.payment-shell--dialog .payment-methods) {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: var(--pos-space-2);
}

:deep(.payment-shell--dialog .payment-method-card) {
	padding: 10px;
	gap: 10px;
}

:deep(.payment-shell--dialog .payment-summary-grid),
:deep(.payment-shell--dialog .invoice-totals-grid),
:deep(.payment-shell--dialog .payments),
:deep(.payment-shell--dialog .selection-fields .v-row) {
	row-gap: 6px;
}

:deep(.payment-shell--dialog .selection-fields p) {
	display: none;
}

:deep(.payment-shell--dialog .payment-summary-grid .v-col),
:deep(.payment-shell--dialog .invoice-totals-grid .v-col),
:deep(.payment-shell--dialog .payments .v-col),
:deep(.payment-shell--dialog .selection-fields .v-col) {
	padding-top: 2px;
	padding-bottom: 2px;
}

:deep(.payment-shell--dialog .payment-section .v-field__input) {
	min-height: 34px;
	padding-top: 4px;
	padding-bottom: 4px;
}

:deep(.payment-shell--dialog .payment-section .v-label) {
	font-size: 0.78rem;
}

:deep(.payment-shell--dialog .payment-section .v-input) {
	font-size: 0.86rem;
}

:deep(.payment-shell--dialog .v-switch) {
	margin-top: 0;
	margin-bottom: 0;
}

:deep(.payment-shell--dialog .v-switch .v-label) {
	font-size: 0.82rem;
}

.submit-highlight {
	box-shadow: 0 0 0 4px rgb(var(--v-theme-primary));
	transition: box-shadow 0.3s ease-in-out;
}

.pos-themed-card {
	background-color: rgb(var(--v-theme-surface));
	color: rgb(var(--v-theme-on-surface));
}

@media (max-width: 768px) {
	.payment-shell {
		display: flex;
		flex-direction: column;
		gap: var(--pos-space-2);
		overflow: visible;
	}

	.payment-card {
		padding: var(--pos-space-1);
		height: auto !important;
		max-height: none !important;
		overflow: visible !important;
	}

	.payment-shell--dialog {
		height: auto;
	}

	.payment-scroll {
		padding: var(--pos-space-2);
		gap: var(--pos-space-2);
		overflow: visible !important;
		min-height: auto;
		max-height: none;
	}

	.payment-sections {
		overflow: visible;
	}

	.payment-sections--dialog {
		grid-template-columns: 1fr;
	}

	:deep(.payment-shell--dialog .payment-methods) {
		grid-template-columns: 1fr;
	}

	.payment-section {
		padding: var(--pos-space-2);
		gap: var(--pos-space-2);
	}

	.payment-footer {
		position: sticky;
		margin-top: 0;
		padding-bottom: calc(env(safe-area-inset-bottom) + 4px);
	}
}
</style>
