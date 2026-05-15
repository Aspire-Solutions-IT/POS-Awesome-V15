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
		customer: "",
		mode: "full",
	}),
	computed: {
		isCollectedMode() {
			return this.mode === "collected";
		},
		dialogTitle() {
			return this.isCollectedMode
				? __("Add Collection Contact")
				: __("Add New Address");
		},
	},

	methods: {
		close_dialog() {
			this.addressDialog = false;
		},

		requiredRule(value) {
			return String(value || "").trim().length > 0 || __("This field is required");
		},

		async submit_dialog() {
			const validation = await this.$refs.addressForm?.validate?.();
			const isValid =
				typeof validation === "boolean"
					? validation
					: validation?.valid !== false;
			if (!isValid) {
				return;
			}

			var vm = this;
			this.address.customer = this.customer;
			this.address.doctype = "Customer";
			if (this.isCollectedMode) {
				this.address.address_line1 =
					String(this.address.address_line1 || "").trim() || __("Customer Collected");
				this.address.city = String(this.address.city || "").trim() || __("Collected");
				this.address.state = String(this.address.state || "").trim() || __("Collected");
				this.address.pincode = String(this.address.pincode || "").trim() || "00000";
				this.address.address_line2 = this.address.address_line2 || "";
			}
			frappe.call({
				method: "posawesome.posawesome.api.customers.make_address",
				args: {
					args: this.address,
				},
				callback: (r) => {
					if (!r.exc) {
						vm.eventBus.emit("add_the_new_address", r.message);
						vm.toastStore.show({
							text: "Customer Address created successfully.",
							color: "success",
						});
						vm.addressDialog = false;
						vm.customer = "";
						vm.address = {};
						vm.mode = "full";
						vm.$nextTick(() => {
							vm.$refs.addressForm?.resetValidation?.();
						});
					}
				},
			});
		},
	},
	created: function () {
		this.eventBus.on("open_new_address", (data) => {
			this.addressDialog = true;
			if (typeof data === "string") {
				this.customer = data;
				this.mode = "full";
			} else {
				this.customer = data?.customer || "";
				this.mode = data?.mode === "collected" ? "collected" : "full";
			}
			this.address = {};
			this.$nextTick(() => {
				this.$refs.addressForm?.resetValidation?.();
			});
		});
	},
};
</script>

<style scoped></style>
