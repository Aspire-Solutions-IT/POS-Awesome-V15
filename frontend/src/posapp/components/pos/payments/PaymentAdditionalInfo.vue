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
			<v-col cols="12" v-if="posProfile.posa_allow_sales_order && invoiceType === 'Order'">
				<div v-if="showCollectFromStoreTag" class="mb-2">
					<v-chip color="primary" variant="tonal" size="small">
						{{ collectFromStoreTagLabel }}
					</v-chip>
				</div>
				<v-autocomplete
					:model-value="selectedShippingAddress"
					:items="addresses"
					:item-title="addressTitle"
					item-value="name"
					:custom-filter="addressFilter"
					:no-data-text="$frappe._('No addresses found')"
					:label="shippingAddressLabel"
					variant="solo"
					density="compact"
					clearable
					:hide-details="shippingAddressError ? false : 'auto'"
					:error="Boolean(shippingAddressError)"
					:error-messages="shippingAddressError ? [shippingAddressError] : []"
					class="sleek-field pos-themed-input"
					@update:model-value="$emit('update:selectedShippingAddress', $event)"
				>
					<template #item="{ props, item }">
						<v-list-item v-bind="props">
							<v-list-item-title>
								{{ addressTitle(item.raw) }}
							</v-list-item-title>
							<v-list-item-subtitle v-if="addressSubtitle(item.raw)">
								{{ addressSubtitle(item.raw) }}
							</v-list-item-subtitle>
						</v-list-item>
					</template>
				</v-autocomplete>
			</v-col>
			<v-col
				cols="12"
				v-if="posProfile.posa_allow_sales_order && invoiceType === 'Order' && showAddressAction"
			>
				<div class="address-action mt-2">
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
			<v-col
				cols="12"
				v-if="
					posProfile.posa_allow_sales_order &&
					invoiceType === 'Order' &&
					showSplitDelivery
				"
			>
				<v-checkbox
					:model-value="splitDelivery"
					:label="$frappe._('Split Delivery')"
					color="primary"
					density="compact"
					hide-details
					@update:model-value="$emit('update:splitDelivery', $event)"
				></v-checkbox>
				<div v-if="splitDeliveryWarningText" class="text-caption text-warning mt-1">
					{{ splitDeliveryWarningText }}
				</div>
			</v-col>
			<v-col
				cols="12"
				md="6"
				v-if="posProfile.posa_allow_sales_order && invoiceType === 'Order' && showPreferredDeliveryDate"
			>
				<v-checkbox
					:model-value="asapDelivery"
					:label="$frappe._('As soon as Available')"
					color="primary"
					density="compact"
					hide-details
					class="mb-1"
					@update:model-value="$emit('update:asapDelivery', $event)"
				></v-checkbox>
				<VueDatePicker
					:model-value="preferredDeliveryDate"
					model-type="yyyy-MM-dd"
					format="dd-MM-yyyy"
					:min-date="preferredDeliveryMinDate"
					:enable-time-picker="false"
					:disabled="asapDelivery"
					auto-apply
					class="sleek-field pos-themed-input"
					:placeholder="preferredDeliveryPlaceholder"
					@update:model-value="$emit('update:preferredDeliveryDate', $event)"
				/>
				<div v-if="preferredDeliveryDateError" class="text-error text-caption mt-1">
					{{ preferredDeliveryDateError }}
				</div>
				<div v-if="holdHelpText" class="text-caption text-medium-emphasis mt-1">
					{{ holdHelpText }}
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
					:label="additionalNotesLabel"
					:hide-details="additionalNotesError ? false : 'auto'"
					:error="Boolean(additionalNotesError)"
					:error-messages="additionalNotesError ? [additionalNotesError] : []"
					v-model="invoiceDoc.posa_notes"
				></v-textarea>
			</v-col>
			<v-col cols="12" v-if="posProfile.posa_display_additional_notes">
				<v-textarea
					class="pa-0 sleek-field"
					variant="solo"
					density="compact"
					clearable
					color="primary"
					auto-grow
					rows="2"
					:label="driverNotesLabel"
					hide-details="auto"
					v-model="invoiceDoc.driver_notes"
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
	shippingAddressLabel: {
		type: String,
		default: "Shipping Address",
	},
	addresses: {
		type: Array,
		default: () => [],
	},
	showAddressAction: {
		type: Boolean,
		default: true,
	},
	showCollectFromStoreTag: {
		type: Boolean,
		default: false,
	},
	showSplitDelivery: {
		type: Boolean,
		default: true,
	},
	showPreferredDeliveryDate: {
		type: Boolean,
		default: false,
	},
	collectFromStoreTagLabel: {
		type: String,
		default: "Collect from Store",
	},
	preferredDeliveryDate: {
		type: String,
		default: null,
	},
	asapDelivery: {
		type: Boolean,
		default: false,
	},
	preferredDeliveryMinDate: {
		type: Date,
		default: () => new Date(),
	},
	selectedShippingAddress: {
		type: String,
		default: null,
	},
	shippingAddressError: {
		type: String,
		default: "",
	},
	splitDelivery: {
		type: [Boolean, Number],
		default: false,
	},
	splitDeliveryWarningText: {
		type: String,
		default: "",
	},
	holdHelpText: {
		type: String,
		default: "",
	},
	holdReleaseDate: {
		type: String,
		default: null,
	},
	holdReleaseMinDate: {
		type: Date,
		default: () => new Date(),
	},
	preferredDeliveryDateError: {
		type: String,
		default: "",
	},
	additionalNotesError: {
		type: String,
		default: "",
	},
	addressFilter: {
		type: Function,
		default: null,
	},
});

defineEmits([
	"update:returnValidUptoDate",
	"update:preferredDeliveryDate",
	"update:asapDelivery",
	"update:selectedShippingAddress",
	"update:splitDelivery",
	"new-address",
]);

const $frappe = inject("frappe", window.frappe);

const addressTitle = (address) =>
	address?.display_title || address?.address_title || address?.address_line1 || address?.name || "";

const addressSubtitle = (address) =>
	[address?.address_line1, address?.city, address?.state, address?.pincode]
		.filter((value) => String(value || "").trim())
		.join(", ");

const preferredDeliveryPlaceholder = `${$frappe._("Earliest Delivery Date")} *`;
const additionalNotesLabel = `${$frappe._("Customer Service Notes")} *`;
const driverNotesLabel = $frappe._("Driver Notes");
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
