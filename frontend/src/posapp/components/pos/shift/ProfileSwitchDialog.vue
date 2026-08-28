<template>
	<v-dialog v-model="isOpen" max-width="640px" scrollable persistent>
		<v-card elevation="8" class="pos-themed-card profile-switch-dialog">
			<v-card-title class="profile-switch-dialog__title">
				<div>
					<div class="profile-switch-dialog__eyebrow">{{ __("Supervisor tools") }}</div>
					<div class="text-h6">{{ __("Switch POS Profile") }}</div>
				</div>
				<v-btn
					icon="mdi-close"
					variant="text"
					:disabled="is_loading"
					:aria-label="__('Close profile switcher')"
					@click="close"
				/>
			</v-card-title>

			<v-card-text>
				<div class="profile-switch-dialog__copy">
					{{
						__(
							"Your current shift stays open. Sales already rung up remain on the profile that made them.",
						)
					}}
				</div>

				<v-alert
					v-if="blocker"
					variant="tonal"
					type="warning"
					density="comfortable"
					class="profile-switch-dialog__blocker"
					data-test="profile-switch-blocker"
				>
					{{ blocker }}
				</v-alert>

				<div v-if="is_fetching" class="profile-switch-dialog__empty">
					{{ __("Loading POS profiles...") }}
				</div>
				<div v-else-if="!selectable_profiles.length" class="profile-switch-dialog__empty">
					{{ __("You are not assigned to any other POS profile.") }}
				</div>
				<div v-else class="profile-switch-dialog__list">
					<button
						v-for="profile in selectable_profiles"
						:key="profile.name"
						type="button"
						:data-test="`profile-option-${profile.name}`"
						class="profile-switch-dialog__option"
						:class="{
							'profile-switch-dialog__option--active': target_profile === profile.name,
						}"
						@click="selectProfile(profile.name)"
					>
						<div>
							<strong>{{ profile.name }}</strong>
							<div class="profile-switch-dialog__meta">
								{{ profile.company }}
								<span v-if="profile.open_shift"> &middot; {{ __("Shift already open") }}</span>
							</div>
						</div>
						<v-icon
							v-if="target_profile === profile.name"
							icon="mdi-check-circle"
							color="primary"
						/>
					</button>
				</div>

				<!-- Opening balances are only collected when the target has no open shift to resume. -->
				<template v-if="target_profile && !resuming">
					<div class="profile-switch-dialog__section">
						<v-icon class="profile-switch-dialog__section-icon">mdi-credit-card-multiple</v-icon>
						{{ __("Opening Balances") }}
					</div>
					<v-data-table
						:headers="payments_methods_headers"
						:items="payments_methods"
						item-key="mode_of_payment"
						:items-per-page="100"
						hide-default-footer
						density="compact"
						fixed-header
						height="220px"
					>
						<template v-slot:item.amount="{ item }">
							<v-text-field
								v-model="item.amount"
								type="number"
								density="compact"
								variant="outlined"
								color="primary"
								hide-details
								:prefix="currencySymbol(item.currency)"
							/>
						</template>
					</v-data-table>
				</template>
				<v-alert
					v-else-if="target_profile && resuming"
					variant="tonal"
					type="info"
					density="comfortable"
					class="profile-switch-dialog__help"
					data-test="profile-switch-resume-note"
				>
					{{ __("An open shift already exists on this profile and will be resumed.") }}
				</v-alert>

				<div class="profile-switch-dialog__section">
					<v-icon class="profile-switch-dialog__section-icon">mdi-shield-account-outline</v-icon>
					{{ __("Supervisor Authorisation") }}
				</div>
				<v-select
					v-model="supervisor_user"
					:items="supervisors"
					item-title="full_name"
					item-value="user"
					variant="outlined"
					density="comfortable"
					hide-details="auto"
					:label="__('Supervisor')"
					data-test="profile-switch-supervisor"
				/>
				<v-text-field
					v-model="pin"
					:type="showPin ? 'text' : 'password'"
					:append-inner-icon="showPin ? 'mdi-eye-off-outline' : 'mdi-eye-outline'"
					variant="outlined"
					density="comfortable"
					hide-details="auto"
					class="mt-3"
					:label="__('Supervisor PIN')"
					data-test="profile-switch-pin"
					autocomplete="new-password"
					name="posa-profile-switch-code"
					data-lpignore="true"
					data-1p-ignore
					data-bwignore
					@keyup.enter="submit"
					@click:append-inner="showPin = !showPin"
				/>

				<v-alert
					v-if="error"
					variant="tonal"
					type="error"
					density="comfortable"
					class="profile-switch-dialog__help"
					data-test="profile-switch-error"
				>
					{{ error }}
				</v-alert>
			</v-card-text>

			<v-card-actions>
				<v-spacer />
				<v-btn variant="text" :disabled="is_loading" @click="close">
					{{ __("Cancel") }}
				</v-btn>
				<v-btn
					color="primary"
					variant="flat"
					:disabled="!can_submit"
					:loading="is_loading"
					data-test="profile-switch-submit"
					@click="submit"
				>
					{{ resuming ? __("Resume Shift") : __("Switch Profile") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { useUIStore } from "../../../stores/uiStore";
import { useInvoiceStore } from "../../../stores/invoiceStore";
import { useEmployeeStore } from "../../../stores/employeeStore";
import { usePosShift } from "../../../composables/pos/shared/usePosShift";

defineOptions({
	name: "ProfileSwitchDialog",
});

const props = defineProps({
	modelValue: Boolean,
});
const emit = defineEmits(["update:modelValue"]);

const __ = window.__ || ((text) => text);
const get_currency_symbol = window.get_currency_symbol;

const uiStore = useUIStore();
const employeeStore = useEmployeeStore();
const { switch_pos_profile } = usePosShift();

// Resolved on demand rather than at setup. invoiceStore reads frappe.datetime when it
// is first created, which is not guaranteed to exist early in the boot sequence.
const cartItemCount = () => {
	try {
		return useInvoiceStore().itemsCount || 0;
	} catch (e) {
		console.warn("Could not read cart state", e);
		return 0;
	}
};

const isOpen = ref(props.modelValue || false);
const is_loading = ref(false);
const is_fetching = ref(false);
const profiles = ref([]);
const payments_method_data = ref([]);
const payments_methods = ref([]);
const target_profile = ref("");
const supervisor_user = ref("");
const pin = ref("");
const showPin = ref(false);
const error = ref("");

const payments_methods_headers = [
	{ title: __("Mode of Payment"), align: "start", sortable: false, value: "mode_of_payment" },
	{ title: __("Opening Amount"), value: "amount", align: "center", sortable: false },
];

const currencySymbol = (currency) => get_currency_symbol?.(currency);

const current_profile_name = computed(() => uiStore.posProfile?.name || "");

const selectable_profiles = computed(() =>
	profiles.value.filter((profile) => profile.name !== current_profile_name.value),
);

const resuming = computed(
	() =>
		!!selectable_profiles.value.find((profile) => profile.name === target_profile.value)
			?.open_shift,
);

const supervisors = computed(() =>
	employeeStore.terminalEmployees.filter((employee) => employee.is_supervisor),
);

// Surfaced up-front rather than only on submit, so the cashier knows why the button
// is dead before they type a PIN.
const blocker = computed(() => {
	if (cartItemCount() > 0) {
		return __("The current sale will be discarded when you switch.");
	}
	return "";
});

const can_submit = computed(
	() => !is_loading.value && !!target_profile.value && !!supervisor_user.value && !!pin.value,
);

watch(
	() => props.modelValue,
	(val) => {
		isOpen.value = !!val;
		if (val) {
			reset();
			load_profiles();
		}
	},
	{ immediate: true },
);

watch(isOpen, (val) => {
	if (!val) {
		emit("update:modelValue", false);
	}
});

watch(target_profile, (val) => {
	payments_methods.value = payments_method_data.value
		.filter((element) => element.parent === val)
		.map((element) => ({ ...element, amount: 0 }));
});

function reset() {
	target_profile.value = "";
	pin.value = "";
	showPin.value = false;
	error.value = "";
	payments_methods.value = [];
	supervisor_user.value =
		supervisors.value.find((employee) => employee.user === employeeStore.currentCashier?.user)
			?.user ||
		supervisors.value[0]?.user ||
		"";
}

function selectProfile(name) {
	target_profile.value = name;
	error.value = "";
}

function close() {
	isOpen.value = false;
	emit("update:modelValue", false);
}

async function load_profiles() {
	is_fetching.value = true;
	error.value = "";
	try {
		const r = await frappe.call(
			"posawesome.posawesome.api.shifts.get_switchable_pos_profiles",
		);
		profiles.value = r?.message?.pos_profiles_data || [];
		payments_method_data.value = r?.message?.payments_method || [];
	} catch (e) {
		console.error("Failed to load switchable POS profiles", e);
		error.value = __("Could not load POS profiles.");
	} finally {
		is_fetching.value = false;
	}
}

async function submit() {
	if (!can_submit.value) {
		return;
	}

	if (cartItemCount() > 0) {
		const confirmed = window.confirm(
			__("Switching POS profile will discard the current sale. Continue?"),
		);
		if (!confirmed) {
			return;
		}
	}

	is_loading.value = true;
	error.value = "";
	try {
		const result = await switch_pos_profile({
			target_profile: target_profile.value,
			balance_details: resuming.value
				? []
				: payments_methods.value.map((method) => ({
						mode_of_payment: method.mode_of_payment,
						opening_amount: method.amount || 0,
					})),
			supervisor_user: supervisor_user.value,
			pin: pin.value,
		});

		if (!result?.success) {
			// The composable toasts offline/pending-sync refusals; server errors surface
			// through Frappe's own message dialog, so only clear the PIN here.
			pin.value = "";
			is_loading.value = false;
			return;
		}
		// On success the terminal reloads; leave the spinner running.
	} catch (e) {
		console.error("Failed to switch POS profile", e);
		error.value = __("Could not switch POS profile.");
		is_loading.value = false;
	}
}
</script>

<style scoped>
.profile-switch-dialog__title {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 12px;
}

.profile-switch-dialog__eyebrow {
	font-size: 0.75rem;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	opacity: 0.7;
}

.profile-switch-dialog__copy {
	margin-bottom: 12px;
	opacity: 0.8;
}

.profile-switch-dialog__blocker,
.profile-switch-dialog__help {
	margin: 12px 0;
}

.profile-switch-dialog__empty {
	padding: 16px 0;
	opacity: 0.7;
}

.profile-switch-dialog__list {
	display: flex;
	flex-direction: column;
	gap: 8px;
}

.profile-switch-dialog__option {
	display: flex;
	align-items: center;
	justify-content: space-between;
	width: 100%;
	padding: 12px 14px;
	border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
	border-radius: 8px;
	text-align: left;
	background: transparent;
	cursor: pointer;
}

.profile-switch-dialog__option--active {
	border-color: rgb(var(--v-theme-primary));
}

.profile-switch-dialog__meta {
	font-size: 0.8rem;
	opacity: 0.7;
}

.profile-switch-dialog__section {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 18px 0 10px;
	font-weight: 600;
}

.profile-switch-dialog__section-icon {
	opacity: 0.7;
}
</style>
