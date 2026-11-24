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
			{{ __("Save address") }}
		</v-btn>
	</div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import {
	DEFAULT_ADDRESS_COUNTRY,
	createOrderAddress,
	orderAddressErrorMessage,
	type OrderAddressInput,
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
	(e: "saved", payload: { name: string; created: boolean; address: OrderAddressInput }): void;
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

// A saved address belongs to one customer and one charge; editing the fields makes it a new one.
watch(
	() => [props.customer, props.deliveryCharge],
	() => {
		Object.assign(form, blank());
		savedName.value = "";
		errorMessage.value = "";
	},
);
watch(form, () => {
	savedName.value = "";
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
	saving.value = true;
	errorMessage.value = "";
	try {
		const result: OrderAddressResult = await createOrderAddress({
			customer: props.customer,
			deliveryCharge: props.deliveryCharge,
			address,
		});
		emit("saved", { ...result, address });
		savedName.value = result.name;
	} catch (error) {
		errorMessage.value = orderAddressErrorMessage(error, __("Could not save the address."));
	} finally {
		saving.value = false;
	}
};
</script>
