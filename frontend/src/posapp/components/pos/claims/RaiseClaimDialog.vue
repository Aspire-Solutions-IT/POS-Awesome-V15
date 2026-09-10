<template>
	<v-dialog :model-value="modelValue" max-width="720" persistent @update:model-value="close">
		<v-card class="pos-themed-card raise-claim-dialog">
			<v-card-title class="d-flex align-center justify-space-between">
				<span>{{ __("Raise Claim") }}</span>
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
						__("Report an issue with {0} for {1}. Submitting records a request for review — no refund, credit or order is created.", [
							salesOrder,
							customerName || __("this customer"),
						])
					}}
				</p>

				<v-alert
					v-if="loadError"
					type="error"
					variant="tonal"
					density="compact"
					border="start"
					class="mb-4"
				>
					{{ loadError }}
				</v-alert>

				<div v-if="loading" class="panel-placeholder">
					{{ __("Loading order…") }}
				</div>

				<template v-else-if="!loadError">
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

					<v-alert
						v-if="overlapWarning"
						type="warning"
						variant="tonal"
						density="compact"
						border="start"
						class="mb-4"
					>
						{{ overlapWarning }}
					</v-alert>

					<v-row dense>
						<v-col cols="12" md="6">
							<v-select
								v-model="form.claim_type"
								:items="claimTypeItems"
								item-title="title"
								item-value="value"
								:label="__('Claim type')"
								density="compact"
								hide-details
								class="pos-themed-input"
							/>
						</v-col>
						<v-col cols="12" md="6">
							<v-select
								v-model="form.preferred_outcome"
								:items="context.preferred_outcomes || []"
								:label="__('Preferred outcome')"
								density="compact"
								hide-details
								class="pos-themed-input"
							/>
						</v-col>
						<v-col v-if="form.preferred_outcome === 'Service Call'" cols="12" md="6">
							<v-select
								v-model="form.service_call_type"
								:items="context.service_call_types || []"
								:label="__('Service type')"
								density="compact"
								hide-details
								class="pos-themed-input"
							/>
						</v-col>
						<v-col cols="12">
							<v-textarea
								v-model="form.description"
								:label="__('What is wrong?')"
								rows="3"
								auto-grow
								hide-details
								class="pos-themed-input"
							/>
						</v-col>
					</v-row>

					<v-alert
						v-if="selectedClaimType?.evidence_instructions"
						type="info"
						variant="tonal"
						density="compact"
						border="start"
						class="mt-4"
					>
						{{ selectedClaimType.evidence_instructions }}
					</v-alert>

					<v-file-input
						v-model="evidenceFile"
						:label="evidenceRequired ? __('Evidence photo (required)') : __('Evidence photo (optional)')"
						accept="image/*,application/pdf"
						prepend-icon="mdi-camera"
						density="compact"
						hide-details
						class="pos-themed-input mt-3"
						:show-size="true"
					/>

					<div class="items-section mt-5">
						<div class="items-section__heading">
							<h3>{{ __("Affected items") }}</h3>
							<span class="text-medium-emphasis">
								{{ __("Tick each item this claim covers and set the affected quantity.") }}
							</span>
						</div>

						<v-table density="compact" class="claim-items-table mt-2">
							<thead>
								<tr>
									<th style="width: 44px"></th>
									<th>{{ __("Item") }}</th>
									<th style="width: 120px">{{ __("Qty") }}</th>
									<th>{{ __("Fault details") }}</th>
								</tr>
							</thead>
							<tbody>
								<tr v-for="row in itemRows" :key="row.sales_order_item">
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
										<div v-if="row.priorClaim" class="text-warning">
											<small>{{ __("On claim {0} ({1})", [row.priorClaim.name, row.priorClaim.workflow_state]) }}</small>
										</div>
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
											v-model="row.fault_details"
											density="compact"
											hide-details
											:disabled="!row.selected"
											:placeholder="__('e.g. screen cracked on arrival')"
											class="pos-themed-input"
										/>
									</td>
								</tr>
							</tbody>
						</v-table>
					</div>
				</template>
			</v-card-text>

			<v-card-actions class="justify-end">
				<v-btn variant="text" :disabled="submitting" @click="close">
					{{ __("Cancel") }}
				</v-btn>
				<v-btn
					color="primary"
					variant="flat"
					:loading="submitting"
					:disabled="submitting || loading || !canSubmit"
					@click="submit"
				>
					{{ __("Submit for review") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import api from "../../../services/api";
import { useToastStore } from "../../../stores/toastStore.js";

declare const __: (value: string, args?: any[]) => string;

type ClaimContextItem = {
	sales_order_item: string;
	item_code: string;
	item_name?: string | null;
	qty?: number | null;
	uom?: string | null;
};

type ClaimType = {
	name: string;
	claim_type_name?: string;
	evidence_required?: number;
	evidence_instructions?: string | null;
};

type ExistingClaim = {
	name: string;
	workflow_state?: string;
	progress?: string;
	items?: Array<{ sales_order_item: string; item_code?: string; qty?: number }>;
};

type ClaimContext = {
	customer?: string;
	company?: string;
	currency?: string;
	items: ClaimContextItem[];
	claim_types: ClaimType[];
	existing_claims: ExistingClaim[];
	preferred_outcomes: string[];
	service_call_types: string[];
};

type ItemRow = {
	sales_order_item: string;
	item_code: string;
	item_name: string;
	maxQty: number;
	selected: boolean;
	qty: number;
	fault_details: string;
	priorClaim: { name: string; workflow_state: string } | null;
};

const props = defineProps<{
	modelValue: boolean;
	salesOrder: string;
	customerName?: string;
}>();

const emit = defineEmits<{
	(e: "update:modelValue", value: boolean): void;
	(e: "created", claimName: string): void;
}>();

const toastStore = useToastStore();

const loading = ref(false);
const loadError = ref("");
const submitting = ref(false);
const submitError = ref("");
const evidenceFile = ref<File | File[] | null>(null);

const emptyContext: ClaimContext = {
	items: [],
	claim_types: [],
	existing_claims: [],
	preferred_outcomes: [],
	service_call_types: [],
};
const context = reactive<ClaimContext>({ ...emptyContext });
const itemRows = ref<ItemRow[]>([]);

const form = reactive({
	claim_type: "",
	preferred_outcome: "",
	service_call_type: "",
	description: "",
});

const claimTypeItems = computed(() =>
	(context.claim_types || []).map((type) => ({
		title: type.claim_type_name || type.name,
		value: type.name,
	})),
);

const selectedClaimType = computed(() =>
	(context.claim_types || []).find((type) => type.name === form.claim_type) || null,
);

const evidenceRequired = computed(() => Number(selectedClaimType.value?.evidence_required || 0) === 1);

const selectedRows = computed(() => itemRows.value.filter((row) => row.selected));

const overlapWarning = computed(() => {
	const clashes = selectedRows.value.filter((row) => row.priorClaim);
	if (!clashes.length) return "";
	const names = [...new Set(clashes.map((row) => row.priorClaim!.name))].join(", ");
	return __(
		"Some selected items are already on an open claim ({0}). Check this is a separate issue before submitting.",
		[names],
	);
});

const evidencePicked = computed(() => {
	const value = evidenceFile.value;
	if (Array.isArray(value)) return value[0] || null;
	return value || null;
});

const canSubmit = computed(() => {
	if (!form.claim_type || !form.preferred_outcome || !form.description.trim()) return false;
	if (form.preferred_outcome === "Service Call" && !form.service_call_type) return false;
	if (evidenceRequired.value && !evidencePicked.value) return false;
	if (!selectedRows.value.length) return false;
	return selectedRows.value.every((row) => Number(row.qty) > 0 && Number(row.qty) <= row.maxQty);
});

function buildRows() {
	const priorByItem = new Map<string, { name: string; workflow_state: string }>();
	for (const claim of context.existing_claims || []) {
		if ((claim.workflow_state || "") === "Rejected") continue;
		for (const line of claim.items || []) {
			if (!priorByItem.has(line.sales_order_item)) {
				priorByItem.set(line.sales_order_item, {
					name: claim.name,
					workflow_state: claim.workflow_state || "",
				});
			}
		}
	}
	itemRows.value = (context.items || []).map((item) => ({
		sales_order_item: item.sales_order_item,
		item_code: item.item_code,
		item_name: item.item_name || "",
		maxQty: Number(item.qty || 0),
		selected: false,
		qty: Number(item.qty || 0),
		fault_details: "",
		priorClaim: priorByItem.get(item.sales_order_item) || null,
	}));
}

function resetForm() {
	form.claim_type = "";
	form.preferred_outcome = "";
	form.service_call_type = "";
	form.description = "";
	evidenceFile.value = null;
	submitError.value = "";
}

async function loadContext() {
	loading.value = true;
	loadError.value = "";
	Object.assign(context, emptyContext);
	itemRows.value = [];
	try {
		const data = await api.call<ClaimContext>(
			"posawesome.posawesome.api.claims.get_sales_order_claim_context",
			{ sales_order: props.salesOrder },
		);
		Object.assign(context, emptyContext, data || {});
		buildRows();
		if (context.claim_types.length === 1) {
			form.claim_type = context.claim_types[0]!.name;
		}
	} catch (error: any) {
		loadError.value =
			error?.message?.message || error?.message || __("Unable to load this Sales Order for a claim.");
	} finally {
		loading.value = false;
	}
}

function fileToBase64(file: File): Promise<string> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => {
			const result = String(reader.result || "");
			const comma = result.indexOf(",");
			resolve(comma >= 0 ? result.slice(comma + 1) : result);
		};
		reader.onerror = () => reject(reader.error);
		reader.readAsDataURL(file);
	});
}

async function uploadEvidence(file: File): Promise<string> {
	const contentBase64 = await fileToBase64(file);
	const uploaded = await api.call<{ file_url?: string }>(
		"posawesome.posawesome.api.claims.upload_claim_evidence",
		{ filename: file.name, content_base64: contentBase64 },
	);
	if (!uploaded?.file_url) {
		throw new Error(__("Evidence upload failed."));
	}
	return uploaded.file_url;
}

async function submit() {
	if (!canSubmit.value || submitting.value) return;
	submitting.value = true;
	submitError.value = "";
	try {
		let evidence = "";
		if (evidencePicked.value) {
			evidence = await uploadEvidence(evidencePicked.value);
		}
		const payload = {
			sales_order: props.salesOrder,
			claim_type: form.claim_type,
			description: form.description.trim(),
			preferred_outcome: form.preferred_outcome,
			service_call_type:
				form.preferred_outcome === "Service Call" ? form.service_call_type : "",
			evidence,
			items: selectedRows.value.map((row) => ({
				sales_order_item: row.sales_order_item,
				qty: Number(row.qty),
				fault_details: row.fault_details.trim(),
			})),
		};
		const result = await api.call<{ name: string }>(
			"posawesome.posawesome.api.claims.raise_claim",
			{ payload },
		);
		toastStore.show({
			title: __("Claim {0} submitted for review", [result.name]),
			color: "success",
		});
		emit("created", result.name);
		emit("update:modelValue", false);
	} catch (error: any) {
		submitError.value =
			error?.message?.message ||
			error?._server_messages ||
			error?.message ||
			__("The claim could not be submitted. Check the details and try again.");
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
		if (open) {
			resetForm();
			void loadContext();
		}
	},
	{ immediate: true },
);
</script>

<style scoped>
.panel-placeholder {
	padding: 24px 0;
	text-align: center;
	color: var(--pos-text-muted, rgba(0, 0, 0, 0.6));
}
.items-section__heading h3 {
	margin: 0;
	font-size: 15px;
}
.claim-items-table td {
	vertical-align: top;
	padding-top: 8px;
	padding-bottom: 8px;
}
.text-warning {
	color: #b26a00;
}
</style>
