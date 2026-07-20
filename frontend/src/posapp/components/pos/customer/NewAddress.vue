<template>
	<v-row justify="center">
		<v-dialog v-model="addressDialog" max-width="600px">
			<v-card>
				<v-card-title>
					<span class="text-h5 text-primary">{{ dialogTitle }}</span>
				</v-card-title>
				<v-card-text class="pa-0">
					<v-container>
						<v-form ref="addressForm" @submit.prevent="submit_dialog">
							<v-row>
								<v-col cols="12">
									<v-text-field
										density="compact"
										color="primary"
										:label="frappe._('Address Name')"
										class="pos-themed-input"
										hide-details="auto"
										:rules="[requiredRule]"
										v-model="address.name"
									></v-text-field>
								</v-col>
								<v-col cols="12" v-if="!isCollectedMode">
									<v-text-field
										density="compact"
										color="primary"
										:label="frappe._('Address Line 1')"
										class="pos-themed-input"
										hide-details="auto"
										:rules="[requiredRule]"
										v-model="address.address_line1"
									></v-text-field>
								</v-col>
								<v-col cols="12" v-if="!isCollectedMode">
									<v-text-field
										density="compact"
										color="primary"
										:label="frappe._('Address Line 2')"
										class="pos-themed-input"
										hide-details
										v-model="address.address_line2"
									></v-text-field>
								</v-col>
								<v-col cols="6" v-if="!isCollectedMode">
									<v-text-field
										:label="frappe._('City')"
										density="compact"
										color="primary"
										class="pos-themed-input"
										hide-details="auto"
										:rules="[requiredRule]"
										v-model="address.city"
									></v-text-field>
								</v-col>
								<v-col cols="6" v-if="!isCollectedMode">
									<v-text-field
										:label="frappe._('County')"
										density="compact"
										class="pos-themed-input"
										hide-details="auto"
										:rules="[requiredRule]"
										v-model="address.state"
									></v-text-field>
								</v-col>
								<v-col cols="6" v-if="!isCollectedMode">
									<v-text-field
										:label="frappe._('Postal Code')"
										density="compact"
										color="primary"
										class="pos-themed-input"
										hide-details="auto"
										:rules="[requiredRule]"
										v-model="address.pincode"
									></v-text-field>
								</v-col>
								<v-col cols="6">
									<v-text-field
										:label="frappe._('Phone')"
										density="compact"
										color="primary"
										class="pos-themed-input"
										hide-details
										v-model="address.phone"
									></v-text-field>
								</v-col>
								<v-col cols="12">
									<v-text-field
										:label="frappe._('Email Address')"
										density="compact"
										color="primary"
										class="pos-themed-input"
										hide-details
										v-model="address.email_id"
									></v-text-field>
								</v-col>
								<v-col cols="12" v-if="!isCollectedMode">
									<v-btn variant="text" color="primary" @click="toggleBillingDetails">
										{{
											showBillingDetails
												? __("Billing address same as shipping")
												: __("Billing address different from shipping")
										}}
									</v-btn>
								</v-col>
								<template v-if="showBillingDetails && !isCollectedMode">
									<v-col cols="12">
										<div class="text-subtitle-2 text-medium-emphasis">
											{{ __("Billing Address Details") }}
										</div>
									</v-col>
									<v-col cols="12">
										<v-text-field
											density="compact"
											color="primary"
											:label="frappe._('Billing Address Name')"
											class="pos-themed-input"
											hide-details="auto"
											v-model="billing_address.name"
										></v-text-field>
									</v-col>
									<v-col cols="12">
										<v-text-field
											density="compact"
											color="primary"
											:label="frappe._('Billing Address Line 1')"
											class="pos-themed-input"
											hide-details="auto"
											v-model="billing_address.address_line1"
										></v-text-field>
									</v-col>
									<v-col cols="12">
										<v-text-field
											density="compact"
											color="primary"
											:label="frappe._('Billing Address Line 2')"
											class="pos-themed-input"
											hide-details
											v-model="billing_address.address_line2"
										></v-text-field>
									</v-col>
									<v-col cols="6">
										<v-text-field
											:label="frappe._('Billing City')"
											density="compact"
											color="primary"
											class="pos-themed-input"
											hide-details="auto"
											v-model="billing_address.city"
										></v-text-field>
									</v-col>
									<v-col cols="6">
										<v-text-field
											:label="frappe._('Billing County')"
											density="compact"
											class="pos-themed-input"
											hide-details="auto"
											v-model="billing_address.state"
										></v-text-field>
									</v-col>
									<v-col cols="6">
										<v-text-field
											:label="frappe._('Billing Postal Code')"
											density="compact"
											color="primary"
											class="pos-themed-input"
											hide-details="auto"
											v-model="billing_address.pincode"
										></v-text-field>
									</v-col>
									<v-col cols="6">
										<v-text-field
											:label="frappe._('Billing Phone')"
											density="compact"
											color="primary"
											class="pos-themed-input"
											hide-details
											v-model="billing_address.phone"
										></v-text-field>
									</v-col>
									<v-col cols="12">
										<v-text-field
											:label="frappe._('Billing Email Address')"
											density="compact"
											color="primary"
											class="pos-themed-input"
											hide-details
											v-model="billing_address.email_id"
										></v-text-field>
									</v-col>
								</template>
							</v-row>
						</v-form>
					</v-container>
				</v-card-text>
				<v-card-actions>
					<v-spacer></v-spacer>
					<v-btn color="error" theme="dark" @click="close_dialog">{{ __("Close") }}</v-btn>
					<v-btn color="success" theme="dark" @click="submit_dialog">{{ __("Submit") }}</v-btn>
				</v-card-actions>
			</v-card>
		</v-dialog>
	</v-row>
</template>

<script>
import { useToastStore } from "../../../stores/toastStore";

export default {
	setup() {
		const toastStore = useToastStore();
		return { toastStore };
	},
	data: () => ({
		addressDialog: false,
		address: {},
		billing_address: {},
		customer: "",
		mode: "full",
		showBillingDetails: false,
		editingAddressName: "",
	}),
	computed: {
		isCollectedMode() {
			return this.mode === "collected";
		},
		dialogTitle() {
			if (this.editingAddressName) {
				return __("Edit Address");
			}
			return this.isCollectedMode ? __("Add Collection Contact") : __("Add New Address");
		},
	},

	methods: {
		close_dialog() {
			this.addressDialog = false;
		},

		requiredRule(value) {
			return String(value || "").trim().length > 0 || __("This field is required");
		},
		toggleBillingDetails() {
			this.showBillingDetails = !this.showBillingDetails;
		},
		callMakeAddress(args) {
			return new Promise((resolve, reject) => {
				frappe.call({
					method: "posawesome.posawesome.api.customers.make_address",
					args: { args },
					callback: (r) => {
						if (!r.exc) {
							resolve(r.message);
							return;
						}
						reject(r.exc);
					},
					error: (e) => reject(e),
				});
			});
		},

		async submit_dialog() {
			const validation = await this.$refs.addressForm?.validate?.();
			const isValid = typeof validation === "boolean" ? validation : validation?.valid !== false;
			if (!isValid) {
				return;
			}

			var vm = this;
			this.address.customer = this.customer;
			this.address.doctype = "Customer";
			this.address.address_type = "Shipping";
			if (this.isCollectedMode) {
				this.address.address_line1 =
					String(this.address.address_line1 || "").trim() || __("Customer Collected");
				this.address.city = String(this.address.city || "").trim() || __("Collected");
				this.address.state = String(this.address.state || "").trim() || __("Collected");
				this.address.pincode = String(this.address.pincode || "").trim() || "00000";
				this.address.address_line2 = this.address.address_line2 || "";
			}
			try {
				const shippingAddress = await this.callMakeAddress(this.address);
				vm.eventBus.emit("add_the_new_address", shippingAddress);

				if (this.showBillingDetails && !this.isCollectedMode) {
					const billingAddress = {
						customer: this.customer,
						doctype: "Customer",
						address_type: "Billing",
						name:
							String(this.billing_address.name || "").trim() ||
							`${this.address.name || shippingAddress?.address_title || this.customer} Billing`,
						address_line1:
							String(this.billing_address.address_line1 || "").trim() ||
							String(this.address.address_line1 || "").trim(),
						address_line2:
							String(this.billing_address.address_line2 || "").trim() ||
							String(this.address.address_line2 || "").trim(),
						city:
							String(this.billing_address.city || "").trim() ||
							String(this.address.city || "").trim(),
						state:
							String(this.billing_address.state || "").trim() ||
							String(this.address.state || "").trim(),
						pincode:
							String(this.billing_address.pincode || "").trim() ||
							String(this.address.pincode || "").trim(),
						phone:
							String(this.billing_address.phone || "").trim() ||
							String(this.address.phone || "").trim(),
						email_id:
							String(this.billing_address.email_id || "").trim() ||
							String(this.address.email_id || "").trim(),
					};
					await this.callMakeAddress(billingAddress);
				}

				vm.toastStore.show({
					text: "Customer Address created successfully.",
					color: "success",
				});
				vm.addressDialog = false;
				vm.customer = "";
				vm.address = {};
				vm.billing_address = {};
				vm.mode = "full";
				vm.showBillingDetails = false;
				vm.editingAddressName = "";
				vm.$nextTick(() => {
					vm.$refs.addressForm?.resetValidation?.();
				});
			} catch (error) {
				console.error("Failed to create customer address", error);
				vm.toastStore.show({
					text: __("Failed to create customer address."),
					color: "error",
				});
			}
		},
	},
	created: function () {
		this.eventBus.on("open_new_address", (data) => {
			this.addressDialog = true;
			if (typeof data === "string") {
				this.customer = data;
				this.mode = "full";
				this.editingAddressName = "";
			} else {
				this.customer = data?.customer || "";
				this.mode = data?.mode === "collected" ? "collected" : "full";
				this.editingAddressName = data?.address?.name || "";
				const sourceAddress = data?.address || {};
				this.address = {
					name: sourceAddress.address_title || sourceAddress.name || "",
					address_line1: sourceAddress.address_line1 || "",
					address_line2: sourceAddress.address_line2 || "",
					city: sourceAddress.city || "",
					state: sourceAddress.state || "",
					pincode: sourceAddress.pincode || "",
					email_id: sourceAddress.email_id || "",
					phone: sourceAddress.phone || "",
					country: sourceAddress.country || "",
				};
			}
			if (!this.editingAddressName) {
				this.address = {};
			}
			this.billing_address = {};
			this.showBillingDetails = false;
			this.$nextTick(() => {
				this.$refs.addressForm?.resetValidation?.();
			});
		});
	},
};
</script>

<style scoped></style>
