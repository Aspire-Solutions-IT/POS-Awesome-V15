<template>
	<v-dialog
		:model-value="modelValue"
		max-width="480"
		persistent
		:retain-focus="false"
		@update:model-value="$emit('update:modelValue', $event)"
	>
		<v-card class="pos-themed-card proforma-confirm">
			<v-card-title class="text-h6">{{ __("Send pro forma") }}</v-card-title>
			<v-card-text>
				<p class="mb-3">
					{{
						customerName
							? __("The pro forma for {0} will be emailed to this address when the order is submitted.", [
									customerName,
								])
							: __("The pro forma will be emailed to this address when the order is submitted.")
					}}
				</p>
				<div v-if="loading" class="proforma-confirm__loading" data-testid="proforma-confirm-loading">
					<v-progress-circular indeterminate size="18" width="2" color="primary" />
					<span>{{ __("Looking up the customer's email…") }}</span>
				</div>
				<v-alert
					v-if="devSiteOverride"
					type="info"
					variant="tonal"
					density="compact"
					class="mb-3"
					data-testid="proforma-confirm-dev"
				>
					{{ __("Dev site: emails go to {0}", [devAddress]) }}
				</v-alert>
				<v-alert
					v-if="lookupFailed"
					type="warning"
					variant="tonal"
					density="compact"
					class="mb-3"
					data-testid="proforma-confirm-lookup-failed"
				>
					{{ __("The customer's email could not be looked up. Enter the address to send to.") }}
				</v-alert>
				<v-text-field
					v-model="recipient"
					:label="__('Send pro forma to')"
					:placeholder="__('Customer email address')"
					:error-messages="error ? [error] : []"
					:disabled="loading"
					density="compact"
					hide-details="auto"
					type="email"
					class="pos-themed-input"
					data-testid="proforma-confirm-recipient"
					@update:model-value="edited = true"
					@keydown.enter.prevent="confirm"
				/>
			</v-card-text>
			<v-card-actions class="justify-end pa-4 pt-0">
				<v-btn variant="text" data-testid="proforma-confirm-cancel" @click="cancel">
					{{ __("Cancel") }}
				</v-btn>
				<v-btn
					color="primary"
					variant="flat"
					:disabled="loading || Boolean(error)"
					data-testid="proforma-confirm-submit"
					@click="confirm"
				>
					{{ __("Send & Submit") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import {
	fetchProformaDefaultRecipient,
	isValidProformaRecipient,
} from "../../../services/proformaService";

defineOptions({ name: "ProformaConfirmDialog" });

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	customer: { type: String, default: "" },
	customerName: { type: String, default: "" },
});
const emit = defineEmits(["update:modelValue", "confirm"]);

const __ = window.__ || ((text) => text);

const recipient = ref("");
const edited = ref(false);
const loading = ref(false);
const lookupFailed = ref(false);
const devSiteOverride = ref(false);
const devAddress = ref("");

// Empty is not allowed here (unlike the resend field): the address is chosen before
// anything is saved, so a customer with no email on file must have one typed.
const error = computed(() => {
	if (loading.value) return "";
	const value = String(recipient.value ?? "").trim();
	if (!value) return __("Enter the email address to send the pro forma to");
	return isValidProformaRecipient(value) ? "" : __("Enter a valid email address");
});

// A lookup for an earlier opening must not fill the field of a later one.
let lookupRun = 0;

const load = async () => {
	const run = ++lookupRun;
	recipient.value = "";
	edited.value = false;
	lookupFailed.value = false;
	devSiteOverride.value = false;
	devAddress.value = "";
	loading.value = true;
	try {
		const result = await fetchProformaDefaultRecipient(props.customer);
		if (run !== lookupRun) return;
		lookupFailed.value = !result.ok;
		devSiteOverride.value = result.devSiteOverride;
		devAddress.value = result.devSiteOverride ? result.recipient : "";
		if (!edited.value) recipient.value = result.recipient;
	} finally {
		if (run === lookupRun) loading.value = false;
	}
};

watch(
	() => props.modelValue,
	(open) => {
		if (open) void load();
		else lookupRun += 1;
	},
	{ immediate: true },
);

const cancel = () => emit("update:modelValue", false);

const confirm = () => {
	if (loading.value || error.value) return;
	emit("confirm", String(recipient.value).trim());
};
</script>

<style scoped>
.proforma-confirm__loading {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 12px;
	font-size: 0.9rem;
	opacity: 0.75;
}
</style>
