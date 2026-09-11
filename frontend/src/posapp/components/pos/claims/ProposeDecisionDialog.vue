<template>
	<v-dialog :model-value="modelValue" max-width="720" persistent @update:model-value="close">
		<v-card class="pos-themed-card propose-decision-dialog">
			<v-card-title class="d-flex align-center justify-space-between">
				<span>{{ __("Propose decision") }}</span>
				<v-btn
					icon="mdi-close"
					variant="text"
					density="comfortable"
					:aria-label="__('Close')"
					:disabled="submitting"
					@click="close"
				/>
			</v-card-title>

			<v-card-text class="pt-2">
				<p class="text-medium-emphasis mb-4">
					{{
						__("An approved decision authorises its actions. {0} stays open as the case.", [
							claim.name,
						])
					}}
				</p>

				<v-alert
					v-if="submitError"
					type="error"
					variant="tonal"
					density="compact"
					border="start"
					class="mb-4"
				>
					{{ submitError }}
				</v-alert>

				<v-row dense>
					<v-col cols="12" md="6">
						<v-select
							v-model="form.outcome"
							:items="outcomes"
							:label="__('Approved outcome')"
							density="compact"
							hide-details
							class="pos-themed-input"
						/>
					</v-col>
					<v-col v-if="form.outcome === 'Service Call'" cols="12" md="6">
						<v-select
							v-model="form.service_call_type"
							:items="serviceCallTypes"
							:label="__('Service type')"
							density="compact"
							hide-details
							class="pos-themed-input"
						/>
					</v-col>
					<v-col cols="12">
						<v-textarea
							v-model="form.reasoning"
							:label="__('Reasoning')"
							:hint="__('Include the explanation when this differs from the customer preference.')"
							persistent-hint
							rows="2"
							auto-grow
							class="pos-themed-input"
						/>
					</v-col>
					<v-col v-if="isMoneyOutcome" cols="12" md="6">
						<v-text-field
							v-model.number="form.amount"
							type="number"
							min="0"
							step="0.01"
							:label="__('Approved amount')"
							:suffix="claim.currency"
							density="compact"
							hide-details
							class="pos-themed-input"
						/>
					</v-col>
					<v-col cols="12" md="6" class="d-flex align-center">
						<v-checkbox
							v-model="form.collection_required"
							:label="__('Collection required')"
							density="compact"
							hide-details
						/>
					</v-col>
					<v-col cols="12">
						<v-textarea
							v-model="form.charge_policy"
							:label="__('Charging / price difference policy (optional)')"
							rows="2"
							auto-grow
							class="pos-themed-input"
						/>
					</v-col>
				</v-row>

				<div class="items-section mt-3">
					<h3>{{ __("Decided items") }}</h3>
					<v-table density="compact" class="decision-items-table mt-1">
						<thead>
							<tr>
								<th style="width: 44px"></th>
								<th>{{ __("Item") }}</th>
								<th style="width: 100px">{{ __("Qty") }}</th>
								<th>{{ __("Replacement / spare part") }}</th>
								<th style="width: 90px">{{ __("Part qty") }}</th>
							</tr>
						</thead>
						<tbody>
							<tr v-for="row in itemRows" :key="row.claim_item">
								<td>
									<v-checkbox
										v-model="row.selected"
										density="compact"
										hide-details
										:aria-label="__('Include {0}', [row.item_code])"
									/>
								</td>
								<td>
									<div>{{ row.item_code }}</div>
									<small class="text-medium-emphasis">{{ row.item_name }}</small>
								</td>
								<td>
									<v-text-field
										v-model.number="row.qty"
										type="number"
										min="0"
										:max="row.maxQty"
										density="compact"
										hide-details
										:disabled="!row.selected"
										class="pos-themed-input"
									/>
								</td>
								<td>
									<v-text-field
										v-model="row.replacement_item"
										density="compact"
										hide-details
										:disabled="!row.selected"
										:placeholder="__('Item code')"
										class="pos-themed-input"
									/>
								</td>
								<td>
									<v-text-field
										v-model.number="row.replacement_qty"
										type="number"
										min="0"
										density="compact"
										hide-details
										:disabled="!row.selected || !row.replacement_item"
										class="pos-themed-input"
									/>
								</td>
							</tr>
						</tbody>
					</v-table>
				</div>
			</v-card-text>

			<v-card-actions class="justify-end">
				<v-btn variant="text" :disabled="submitting" @click="close">{{ __("Cancel") }}</v-btn>
				<v-btn
					color="primary"
					variant="flat"
					:loading="submitting"
					:disabled="submitting || !canSubmit"
					@click="submit"
				>
					{{ __("Record decision") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import api from "../../../services/api";

declare const __: (value: string, args?: any[]) => string;

type DecisionItemRow = {
	claim_item: string;
	item_code: string;
	item_name: string;
	maxQty: number;
	selected: boolean;
	qty: number;
	replacement_item: string;
	replacement_qty: number;
};

const props = defineProps<{
	modelValue: boolean;
	claim: {
		name: string;
		currency?: string;
		preferred_outcome?: string;
		items?: Array<Record<string, any>>;
	};
}>();

const emit = defineEmits<{
	(e: "update:modelValue", value: boolean): void;
	(e: "created", claimName: string): void;
}>();

const outcomes = ["Exchange", "Refund", "Credit", "Replace", "Service Call"];
const serviceCallTypes = ["Maintenance Visit", "Spare Part"];

const submitting = ref(false);
const submitError = ref("");
const itemRows = ref<DecisionItemRow[]>([]);

const form = reactive({
	outcome: "",
	service_call_type: "",
	reasoning: "",
	amount: 0,
	collection_required: false,
	charge_policy: "",
});

const isMoneyOutcome = computed(() => form.outcome === "Refund" || form.outcome === "Credit");
const selectedRows = computed(() => itemRows.value.filter((row) => row.selected));

const canSubmit = computed(() => {
	if (!form.outcome || !form.reasoning.trim()) return false;
	if (form.outcome === "Service Call" && !form.service_call_type) return false;
	if (isMoneyOutcome.value && !(Number(form.amount) > 0)) return false;
	if (!selectedRows.value.length) return false;
	const needsReplacement = form.outcome === "Exchange" || form.outcome === "Replace";
	return selectedRows.value.every((row) => {
		if (!(Number(row.qty) > 0 && Number(row.qty) <= row.maxQty)) return false;
		if (needsReplacement && !row.replacement_item) return false;
		return true;
	});
});

function resetForm() {
	form.outcome = props.claim.preferred_outcome || "";
	form.service_call_type = "";
	form.reasoning = "";
	form.amount = 0;
	form.collection_required = false;
	form.charge_policy = "";
	submitError.value = "";
	itemRows.value = (props.claim.items || []).map((item) => ({
		claim_item: item.name,
		item_code: item.item_code,
		item_name: item.item_name || "",
		maxQty: Number(item.qty || 0),
		selected: false,
		qty: Number(item.qty || 0),
		replacement_item: "",
		replacement_qty: 0,
	}));
}

async function submit() {
	if (!canSubmit.value || submitting.value) return;
	submitting.value = true;
	submitError.value = "";
	try {
		const payload = {
			claim: props.claim.name,
			outcome: form.outcome,
			service_call_type: form.outcome === "Service Call" ? form.service_call_type : "",
			reasoning: form.reasoning.trim(),
			amount: isMoneyOutcome.value ? Number(form.amount) : 0,
			collection_required: form.collection_required ? 1 : 0,
			charge_policy: form.charge_policy.trim(),
			items: selectedRows.value.map((row) => ({
				claim_item: row.claim_item,
				qty: Number(row.qty),
				replacement_item: row.replacement_item || "",
				replacement_qty: row.replacement_item ? Number(row.replacement_qty || 0) : 0,
			})),
		};
		await api.call("posawesome.posawesome.api.claims.propose_decision", { payload });
		emit("created", props.claim.name);
		emit("update:modelValue", false);
	} catch (error: any) {
		submitError.value =
			error?.message?.message ||
			error?.message ||
			__("The decision could not be recorded. Check the details and try again.");
	} finally {
		submitting.value = false;
	}
}

function close() {
	if (submitting.value) return;
	emit("update:modelValue", false);
}

watch(
	() => props.modelValue,
	(open) => {
		if (open) resetForm();
	},
	{ immediate: true },
);
</script>

<style scoped>
.items-section h3 {
	margin: 0;
	font-size: 15px;
}
.decision-items-table td {
	vertical-align: top;
	padding-top: 8px;
	padding-bottom: 8px;
}
</style>
