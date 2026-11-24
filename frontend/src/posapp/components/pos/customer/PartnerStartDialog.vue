<template>
	<v-dialog :model-value="open" persistent max-width="560" :retain-focus="false">
		<v-card class="partner-start-dialog" elevation="8">
			<v-card-title class="pt-5 px-6">
				<div class="text-h6">{{ __("Who is this order for?") }}</div>
				<div class="text-body-2 text-medium-emphasis">
					{{ __("Choose the customer and delivery address to start.") }}
				</div>
			</v-card-title>
			<v-card-text class="px-6">
				<v-autocomplete
					v-model="pickedCustomer"
					:items="customerItems"
					:loading="loadingCustomers"
					:label="__('Customer')"
					:no-data-text="__('Customers not found')"
					item-title="customer_name"
					item-value="name"
					variant="outlined"
					density="comfortable"
					prepend-inner-icon="mdi-account"
					:custom-filter="() => true"
					autofocus
					@update:search="onSearch"
					@update:model-value="onCustomerPicked"
				/>
				<v-select
					v-model="pickedAddress"
					:items="addressItems"
					:loading="loadingAddresses"
					:disabled="!pickedCustomer"
					:label="__('Delivery address')"
					:no-data-text="__('This customer has no delivery address')"
					item-title="title"
					item-value="name"
					variant="outlined"
					density="comfortable"
					prepend-inner-icon="mdi-truck-delivery"
					class="mt-2"
				/>
				<v-alert
					v-if="pickedCustomer && !loadingAddresses && !addressItems.length"
					type="warning"
					variant="tonal"
					density="compact"
				>
					{{ __("This customer has no delivery address on file. Ask the office to add one.") }}
				</v-alert>
			</v-card-text>
			<v-card-actions class="px-6 pb-5">
				<v-btn v-if="confirmedCustomer" variant="text" @click="cancel">{{ __("Cancel") }}</v-btn>
				<v-spacer />
				<v-btn color="primary" variant="flat" :disabled="!canContinue" @click="confirm">
					{{ __("Start order") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { storeToRefs } from "pinia";
import _ from "lodash";
import { isPartnerMode } from "../../../utils/partnerMode";
import { partnerStartRequested } from "../../../utils/partnerStartRequest";
import { useCustomersStore } from "../../../stores/customersStore.js";
import { useInvoiceStore } from "../../../stores/invoiceStore.js";

declare const frappe: any;
declare const __: (text: string) => string;

const props = defineProps<{ active: boolean }>();

const customersStore = useCustomersStore();
const invoiceStore = useInvoiceStore();
const { filteredCustomers, loadingCustomers, selectedCustomer } = storeToRefs(customersStore);
const { invoiceDoc } = storeToRefs(invoiceStore);

const partner = isPartnerMode();
const confirmedCustomer = ref<string | null>(null);
const confirmedAddress = ref<string | null>(null);
const pickedCustomer = ref<string | null>(null);
const pickedAddress = ref<string | null>(null);
const addresses = ref<any[]>([]);
const loadingAddresses = ref(false);

// Open until a customer + address are confirmed, whenever the partner clicks the Customer
// box, and if a different customer gets selected some other way (it needs an address too).
const open = computed(
	() =>
		partner &&
		props.active &&
		(partnerStartRequested.value ||
			!confirmedCustomer.value ||
			(!!selectedCustomer.value && selectedCustomer.value !== confirmedCustomer.value)),
);

const customerItems = computed(() => filteredCustomers.value || []);
const addressItems = computed(() =>
	addresses.value.map((row) => ({
		name: row.name,
		title:
			[row.address_title, row.address_line1, row.city, row.pincode]
				.filter(Boolean)
				.join(", ") || row.name,
	})),
);
const canContinue = computed(() => !!pickedCustomer.value && !!pickedAddress.value);

const onSearch = _.debounce((term: string) => {
	// Skip the echo of the selected item's own title into the search box.
	if (term && customerItems.value.some((c: any) => c.customer_name === term)) return;
	void customersStore.queueSearch(term || "");
}, 300);

let addressRequest = 0;
const onCustomerPicked = async (customer: string | null, keepAddress: string | null = null) => {
	pickedAddress.value = null;
	addresses.value = [];
	if (!customer) return;
	const request = ++addressRequest;
	loadingAddresses.value = true;
	try {
		const rows = await frappe.xcall("posawesome.posawesome.api.customers.get_customer_addresses", {
			customer,
		});
		if (request !== addressRequest) return;
		addresses.value = Array.isArray(rows) ? rows : [];
		if (keepAddress && addresses.value.some((row) => row.name === keepAddress)) {
			pickedAddress.value = keepAddress;
		} else if (addresses.value.length === 1) {
			// A single address needs no decision; with several, the partner must choose.
			pickedAddress.value = addresses.value[0].name;
		}
	} catch (error) {
		console.error("Failed to load customer addresses", error);
	} finally {
		if (request === addressRequest) loadingAddresses.value = false;
	}
};

const applyAddress = () => {
	const doc = invoiceDoc.value;
	if (!doc || !confirmedAddress.value || doc.customer !== confirmedCustomer.value) return;
	// Only refill an empty address: the order code clears it in several places (delivery
	// charge, date, order type), but a partner's own pick in Payments must stick.
	if (doc.shipping_address_name) return;
	invoiceStore.mergeInvoiceDoc({
		shipping_address_name: confirmedAddress.value,
		customer_address: confirmedAddress.value,
	});
};

const confirm = () => {
	if (!canContinue.value) return;
	confirmedCustomer.value = pickedCustomer.value;
	confirmedAddress.value = pickedAddress.value;
	partnerStartRequested.value = false;
	// Fills the normal Customer box, which in turn loads the customer into the order.
	customersStore.setSelectedCustomer(confirmedCustomer.value);
	// Same customer re-confirmed with a new address: replace the order's address now.
	if (invoiceDoc.value?.customer === confirmedCustomer.value) {
		invoiceStore.mergeInvoiceDoc({
			shipping_address_name: confirmedAddress.value,
			customer_address: confirmedAddress.value,
		});
	}
};

const cancel = () => {
	partnerStartRequested.value = false;
	// Leave the Customer box showing the customer the order is actually for.
	if (confirmedCustomer.value) customersStore.setSelectedCustomer(confirmedCustomer.value);
};

watch(() => [invoiceDoc.value?.customer, invoiceDoc.value?.shipping_address_name], applyAddress);

// Prefill with the current customer (and address) whenever the dialog opens.
watch(open, (isOpen) => {
	if (!isOpen) return;
	const customer = confirmedCustomer.value || selectedCustomer.value;
	if (customer && customer !== pickedCustomer.value) {
		pickedCustomer.value = customer;
		void onCustomerPicked(customer, customer === confirmedCustomer.value ? confirmedAddress.value : null);
	}
});
</script>
