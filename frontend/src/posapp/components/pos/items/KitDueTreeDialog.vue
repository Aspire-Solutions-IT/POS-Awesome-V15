<template>
	<v-dialog
		:model-value="modelValue"
		@update:model-value="$emit('update:modelValue', $event)"
		max-width="900"
		scrollable
	>
		<v-card>
			<v-card-title class="d-flex align-center text-h6">
				<v-icon class="mr-2">mdi-file-tree</v-icon>
				<span class="kit-tree-title">{{ __("Component Due Dates") }} — {{ itemName || itemCode }}</span>
				<v-spacer></v-spacer>
				<v-btn icon="mdi-close" variant="text" size="small" @click="$emit('update:modelValue', false)" />
			</v-card-title>
			<v-divider></v-divider>
			<v-card-text class="pa-0">
				<div v-if="loading" class="pa-6 d-flex justify-center">
					<v-progress-circular indeterminate color="primary" />
				</div>
				<v-alert v-else-if="error" type="error" variant="tonal" class="ma-4">{{ error }}</v-alert>
				<v-table v-else density="compact" class="kit-tree-table">
					<thead>
						<tr>
							<th>{{ __("Item") }}</th>
							<th class="text-end">{{ __("Qty per Kit") }}</th>
							<th class="text-end">{{ __("Available") }}</th>
							<th class="text-end">{{ __("Due In QTY") }}</th>
							<th class="text-end">{{ __("Due") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="row in rows" :key="row.key" :class="{ 'kit-tree-root': row.depth === 0 }">
							<td>
								<div class="kit-tree-item" :style="{ paddingLeft: `${row.depth * 20}px` }">
									<v-btn
										v-if="row.hasChildren"
										:icon="collapsed.has(row.key) ? 'mdi-chevron-right' : 'mdi-chevron-down'"
										variant="text"
										size="x-small"
										density="comfortable"
										@click="toggle(row.key)"
									/>
									<span v-else class="kit-tree-spacer"></span>
									<div>
										<div class="kit-tree-name">
											{{ row.node.item_name }}
											<v-chip
												v-if="row.node.is_kit_set"
												size="x-small"
												color="blue-darken-3"
												variant="tonal"
												class="ml-1"
												>{{ __("Kit Set") }}</v-chip
											>
											<v-chip
												v-else-if="row.node.is_kit_item"
												size="x-small"
												color="primary"
												variant="tonal"
												class="ml-1"
												>{{ __("Kit") }}</v-chip
											>
											<v-tooltip v-if="row.node.cycle" location="top">
												<template #activator="{ props: tip }">
													<v-icon v-bind="tip" size="small" color="warning" class="ml-1"
														>mdi-alert</v-icon
													>
												</template>
												{{ __("This kit contains itself; not expanded further.") }}
											</v-tooltip>
										</div>
										<div
											v-if="row.node.item_name !== row.node.item_code"
											class="kit-tree-code"
										>
											{{ row.node.item_code }}
										</div>
									</div>
								</div>
							</td>
							<td class="text-end">{{ row.depth === 0 ? "-" : formatQty(row.node.total_qty) }}</td>
							<td class="text-end">{{ formatQty(row.node.available_qty) }}</td>
							<td class="text-end">{{ formatQty(row.node.quantity_due_in) }}</td>
							<td class="text-end">{{ formatDueDate(row.node.next_due_date) }}</td>
						</tr>
					</tbody>
				</v-table>
			</v-card-text>
		</v-card>
	</v-dialog>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { flattenKitDueTree } from "../../../utils/kitDueTree";

defineOptions({
	name: "KitDueTreeDialog",
});

const props = defineProps({
	modelValue: { type: Boolean, default: false },
	itemCode: { type: String, default: "" },
	itemName: { type: String, default: "" },
	formatQty: { type: Function, required: true },
	formatDueDate: { type: Function, required: true },
});

defineEmits(["update:modelValue"]);

const __ = window.__ || ((text) => text);

const tree = ref(null);
const loading = ref(false);
const error = ref("");
const collapsed = ref(new Set());
let requestId = 0;

const rows = computed(() => flattenKitDueTree(tree.value, collapsed.value));

const toggle = (key) => {
	const next = new Set(collapsed.value);
	if (next.has(key)) next.delete(key);
	else next.add(key);
	collapsed.value = next;
};

const load = async () => {
	const current = ++requestId;
	tree.value = null;
	error.value = "";
	collapsed.value = new Set();
	loading.value = true;
	try {
		const res = await frappe.call({
			method: "posawesome.posawesome.api.kit_due_tree.get_kit_due_tree",
			args: { item_code: props.itemCode },
		});
		if (current !== requestId) return;
		tree.value = res?.message || null;
	} catch (e) {
		if (current !== requestId) return;
		error.value = __("Could not load kit components.");
	} finally {
		if (current === requestId) loading.value = false;
	}
};

watch(
	() => [props.modelValue, props.itemCode],
	([open, code]) => {
		if (open && code) load();
	},
	{ immediate: true },
);
</script>

<style scoped>
.kit-tree-title {
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.kit-tree-item {
	display: flex;
	align-items: center;
	gap: 4px;
}

.kit-tree-spacer {
	display: inline-block;
	width: 28px;
	flex-shrink: 0;
}

.kit-tree-name {
	font-weight: 500;
}

.kit-tree-code {
	font-size: 0.75rem;
	color: var(--pos-text-secondary);
}

.kit-tree-root td {
	font-weight: 600;
	background-color: rgba(var(--v-theme-primary), 0.06);
}
</style>
