<template>
	<div v-if="invoiceDoc">
		<!-- Additional Invoice Information (Delivery, Address, Notes) -->
		<v-row class="pa-1">
			<v-col cols="6" v-if="returnValidityEnabled && !invoiceDoc.is_return">
				<VueDatePicker
					:model-value="returnValidUptoDate"
					model-type="format"
					format="dd-MM-yyyy"
					:min-date="returnValidityMinDate"
					:enable-time-picker="false"
					auto-apply
					class="sleek-field pos-themed-input"
					:placeholder="$frappe._('Return Valid Until')"
					@update:model-value="$emit('update:returnValidUptoDate', $event)"
				/>
			</v-col>
			<!-- Shipping Address action -->
			<v-col cols="12" v-if="posProfile.posa_allow_sales_order && invoiceType === 'Order'">
				<div class="address-action">
					<v-btn
						icon="mdi-plus"
						color="primary"
						variant="tonal"
						size="small"
						:aria-label="addressActionLabel"
						@click="$emit('new-address')"
					></v-btn>
					<span class="address-action__label">
						{{ addressActionLabel }}
					</span>
				</div>
			</v-col>

			<!-- Additional Notes (if enabled in POS profile) -->
			<v-col cols="12" v-if="posProfile.posa_display_additional_notes">
				<v-textarea
					class="pa-0 sleek-field"
					variant="solo"
					density="compact"
					clearable
					color="primary"
					auto-grow
					rows="2"
					:label="$frappe._('Additional Notes')"
					v-model="invoiceDoc.posa_notes"
				></v-textarea>
			</v-col>
			<v-col cols="12" md="6" v-if="posProfile.posa_display_authorization_code">
				<v-text-field
					class="sleek-field pos-themed-input"
					variant="solo"
					density="compact"
					clearable
					color="primary"
					:label="$frappe._('Authorization Code')"
					v-model="invoiceDoc.posa_authorization_code"
					hide-details
					autocomplete="off"
					maxlength="32"
				></v-text-field>
			</v-col>
		</v-row>
	</div>
</template>

<script setup>
import { inject } from "vue";

defineProps({
	invoiceDoc: {
		type: Object,
		required: true,
	},
	posProfile: {
		type: [Object, String],
		default: () => ({}),
	},
	invoiceType: {
		type: String,
		default: "Invoice",
	},
	returnValidityEnabled: {
		type: Boolean,
		default: false,
	},
	returnValidityMinDate: {
		type: Date,
		default: () => new Date(),
	},
	returnValidUptoDate: {
		type: String,
		default: null,
	},
	addressActionLabel: {
		type: String,
		default: "Add Customer Address",
	},
});

defineEmits(["update:returnValidUptoDate", "new-address"]);

const $frappe = inject("frappe", window.frappe);
</script>

<style scoped>
.pos-themed-input :deep(.v-field__input) {
	font-weight: 500;
}

.address-action {
	align-items: center;
	display: flex;
	gap: 10px;
	min-height: 40px;
}

.address-action__label {
	font-size: 0.95rem;
	font-weight: 500;
}
</style>
