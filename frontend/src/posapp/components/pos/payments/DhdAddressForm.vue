<template>
	<div class="dhd-address-form" data-test="dhd-address-form">
		<div class="text-subtitle-2 mb-2">{{ __("Delivery address") }}</div>
		<v-row dense>
			<v-col cols="12">
				<v-text-field
					v-model="form.address_line1"
					:label="__('Address line 1') + ' *'"
					data-test="dhd-line1"
					v-bind="fieldProps"
				/>
			</v-col>
			<v-col cols="12">
				<v-text-field
					v-model="form.address_line2"
					:label="__('Address line 2')"
					data-test="dhd-line2"
					v-bind="fieldProps"
				/>
			</v-col>
			<v-col cols="12" md="6">
				<v-text-field
					v-model="form.city"
					:label="__('City') + ' *'"
					data-test="dhd-city"
					v-bind="fieldProps"
				/>
			</v-col>
			<v-col cols="12" md="6">
				<v-text-field
					v-model="form.county"
					:label="__('County')"
					data-test="dhd-county"
					v-bind="fieldProps"
				/>
			</v-col>
			<v-col cols="12" md="6">
				<v-text-field
					v-model="form.pincode"
					:label="__('Postcode') + ' *'"
					data-test="dhd-postcode"
					v-bind="fieldProps"
				/>
			</v-col>
			<v-col cols="12" md="6">
				<v-text-field
					v-model="form.country"
					:label="__('Country') + ' *'"
					data-test="dhd-country"
					v-bind="fieldProps"
				/>
			</v-col>
			<v-col cols="12" md="6">
				<v-text-field
					v-model="form.phone"
					:label="__('Phone')"
					data-test="dhd-phone"
					v-bind="fieldProps"
				/>
			</v-col>
			<v-col cols="12" md="6">
				<v-text-field
					v-model="form.email_id"
					:label="__('Email (optional)')"
					data-test="dhd-email"
					v-bind="fieldProps"
				/>
			</v-col>
		</v-row>
		<div v-if="errorMessage" class="text-error text-caption mt-1" data-test="dhd-error" role="alert">
			{{ errorMessage }}
		</div>
		<div v-if="saving" class="text-caption mt-1" data-test="dhd-saving">
			{{ __("Saving the address and selecting it…") }}
		</div>
		<div v-if="savedName" class="text-success text-caption mt-1" data-test="dhd-saved">
			{{ __("Saved address") }}: {{ savedName }}
		</div>
		<v-btn
			color="primary"
			variant="tonal"
			size="small"
			class="mt-2"
			:loading="saving"
			:disabled="saving || !canSave"
			data-test="dhd-save"
			@click="save"
		>
			{{ saving ? __("Saving…") : retryable ? __("Retry") : __("Save address") }}
		</v-btn>
	</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from "vue";
import {
	DEFAULT_ADDRESS_COUNTRY,
	createOrderAddress,
	orderAddressErrorMessage,
	type OrderAddressInput,
	type DhdSaveSettlement,
	type OrderAddressResult,
} from "../../../services/orderAddressService";
import { isValidOptionalEmail } from "../../../utils/emailValidation";

const __: (text: string, args?: unknown[]) => string =
	(window as any).__ || ((text: string) => text);

const props = defineProps<{
	customer: string;
	deliveryCharge: string;
}>();

const emit = defineEmits<{
	// A save began: the parent must treat the previous selection as stale until it is settled.
	(e: "saving", payload: { saveId: number; customer: string; deliveryCharge: string }): void;
	// The POST succeeded. Nothing is done until the parent calls `settle`.
	(
		e: "saved",
		payload: {
			saveId: number;
			name: string;
			created: boolean;
			address: OrderAddressInput;
			customer: string;
			deliveryCharge: string;
			settle: (result: DhdSaveSettlement) => void;
		},
	): void;
	// The save ended without a selected address ("failed" POST, or "cancelled" by an edit, a reset
	// or an unmount).
	(e: "save-ended", payload: { saveId: number; reason: "failed" | "cancelled" }): void;
}>();

const blank = (): OrderAddressInput => ({
	address_line1: "",
	address_line2: "",
	city: "",
	county: "",
	pincode: "",
	country: DEFAULT_ADDRESS_COUNTRY,
	phone: "",
	email_id: "",
});

const form = reactive<OrderAddressInput>(blank());
const saving = ref(false);
const errorMessage = ref("");
const savedName = ref("");
// The address was saved but could not be selected: Save becomes a retry.
const retryable = ref(false);

const fieldProps = {
	variant: "solo",
	density: "compact",
	"hide-details": "auto",
	class: "sleek-field pos-themed-input",
} as const;

const trimmed = (): OrderAddressInput => {
	const out: Record<string, string> = {};
	for (const [key, value] of Object.entries(form)) {
		out[key] = String(value ?? "").trim();
	}
	return out as unknown as OrderAddressInput;
};

const canSave = computed(() => {
	const v = trimmed();
	return Boolean(v.address_line1 && v.city && v.pincode && v.country) && Boolean(props.customer);
});

// Each Save owns a token covering the POST *and* the parent's picker reload. A reset
// (customer/charge change), an edit or an unmount invalidates the token, so a result that arrives
// afterwards is thrown away instead of being applied.
let requestToken = 0;

// Abandon the save in flight, if any, and tell the parent so it stops waiting on it.
const cancelPending = () => {
	if (!saving.value) {
		return;
	}
	const saveId = requestToken;
	requestToken += 1;
	saving.value = false;
	emit("save-ended", { saveId, reason: "cancelled" });
};

// A saved address belongs to one customer and one charge; editing the fields makes it a new one.
watch(
	() => [props.customer, props.deliveryCharge],
	() => {
		cancelPending();
		requestToken += 1;
		saving.value = false;
		Object.assign(form, blank());
		savedName.value = "";
		errorMessage.value = "";
		retryable.value = false;
	},
);
watch(form, () => {
	cancelPending();
	savedName.value = "";
	retryable.value = false;
});
onBeforeUnmount(() => {
	cancelPending();
	requestToken += 1;
});

const save = async () => {
	if (saving.value || !canSave.value) {
		return;
	}
	const address = trimmed();
	if (!isValidOptionalEmail(address.email_id)) {
		errorMessage.value = __("Enter a valid email address.");
		return;
	}
	const customer = props.customer;
	const deliveryCharge = props.deliveryCharge;
	const token = ++requestToken;
	const snapshot = JSON.stringify(address);
	// Still the same Save, for the same checkout, with the same typed address.
	const isCurrent = () =>
		token === requestToken &&
		props.customer === customer &&
		props.deliveryCharge === deliveryCharge &&
		JSON.stringify(trimmed()) === snapshot;
	saving.value = true;
	retryable.value = false;
	errorMessage.value = "";
	emit("saving", { saveId: token, customer, deliveryCharge });
	let result: OrderAddressResult;
	try {
		result = await createOrderAddress({ customer, deliveryCharge, address });
	} catch (error) {
		if (isCurrent()) {
			errorMessage.value = orderAddressErrorMessage(error, __("Could not save the address."));
			saving.value = false;
			emit("save-ended", { saveId: token, reason: "failed" });
		}
		return;
	}
	if (!isCurrent()) {
		return;
	}
	// Stay pending until the parent confirms the new address is the selected one.
	emit("saved", {
		...result,
		saveId: token,
		address,
		customer,
		deliveryCharge,
		settle: (settlement) => {
			if (!isCurrent()) {
				return;
			}
			saving.value = false;
			if (settlement.status === "confirmed") {
				savedName.value = result.name;
			} else if (settlement.status === "failed") {
				retryable.value = true;
				errorMessage.value =
					settlement.message ||
					__("The address was saved but could not be selected. Press Retry.");
			}
		},
	});
};
</script>
