<template>
	<div class="split-groups">
		<div class="split-groups__toolbar">
			<v-btn color="primary" variant="tonal" @click="createGroup">
				{{ $frappe._("Add Group") }}
			</v-btn>
		</div>

		<v-row class="split-groups__summary" dense>
			<v-col v-for="group in groups" :key="group.group_id" cols="12" md="6" xl="4">
				<div class="split-groups__summary-card">
					<div class="split-groups__summary-head">
						<span class="split-groups__summary-label">{{ group.label }}</span>
						<span class="split-groups__summary-value">
							{{ formatCurrency(groupTotals[group.group_id] || 0) }}
						</span>
					</div>
					<div class="split-groups__summary-meta">
						{{ groupItemCounts[group.group_id] || 0 }} {{ $frappe._("item(s)") }}
					</div>
				</div>
			</v-col>
		</v-row>

		<div class="split-groups__list">
			<div v-for="group in groups" :key="group.group_id" class="split-groups__group">
				<div class="split-groups__group-head">
					<div class="split-groups__group-title">{{ group.label }}</div>
					<v-btn
						v-if="group.group_id !== defaultGroupId"
						color="error"
						variant="text"
						size="small"
						@click="$emit('remove-group', group.group_id)"
					>
						{{ $frappe._("Remove") }}
					</v-btn>
				</div>

				<div v-if="groupItems[group.group_id]?.length" class="split-groups__items">
					<div
						v-for="item in groupItems[group.group_id]"
						:key="item.posa_row_id"
						class="split-groups__item"
					>
						<div class="split-groups__item-copy">
							<div class="split-groups__item-name">{{ item.item_name || item.item_code }}</div>
							<div class="split-groups__item-meta">
								{{ item.item_code }} • {{ item.qty }} × {{ formatCurrency(item.rate || 0) }}
							</div>
						</div>
						<div class="split-groups__item-actions">
							<div class="split-groups__item-total">
								{{ formatCurrency(item.amount || item.qty * item.rate || 0) }}
							</div>
							<v-select
								:model-value="group.group_id"
								:items="groupOptions"
								item-title="label"
								item-value="value"
								variant="solo"
								density="compact"
								hide-details
								class="sleek-field pos-themed-input split-groups__item-select"
								@update:model-value="
									$emit('move-item', {
										rowId: item.posa_row_id,
										groupId: $event,
									})
								"
							></v-select>
						</div>
					</div>
				</div>
				<div v-else class="split-groups__empty">
					{{ $frappe._("No items in this group yet.") }}
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, inject } from "vue";

const props = defineProps({
	groups: {
		type: Array,
		default: () => [],
	},
	items: {
		type: Array,
		default: () => [],
	},
	defaultGroupId: {
		type: String,
		required: true,
	},
	formatCurrency: {
		type: Function,
		required: true,
	},
});

const emit = defineEmits(["create-group", "remove-group", "move-item"]);

const $frappe = inject("frappe", window.frappe);

const groupOptions = computed(() =>
	(props.groups || []).map((group) => ({
		label: group.label,
		value: group.group_id,
	})),
);

const groupItems = computed(() => {
	const itemMap = new Map((props.items || []).map((item) => [item.posa_row_id, item]));
	const mapped = {};
	(props.groups || []).forEach((group) => {
		mapped[group.group_id] = (group.row_ids || [])
			.map((rowId) => itemMap.get(rowId))
			.filter(Boolean);
	});
	return mapped;
});

const groupTotals = computed(() => {
	const totals = {};
	Object.entries(groupItems.value).forEach(([groupId, items]) => {
		totals[groupId] = (items || []).reduce(
			(sum, item) => sum + Number(item?.amount || Number(item?.qty || 0) * Number(item?.rate || 0)),
			0,
		);
	});
	return totals;
});

const groupItemCounts = computed(() => {
	const counts = {};
	Object.entries(groupItems.value).forEach(([groupId, items]) => {
		counts[groupId] = (items || []).length;
	});
	return counts;
});

const createGroup = () => {
	emit("create-group");
};
</script>

<style scoped>
.split-groups {
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.split-groups__toolbar {
	display: flex;
	justify-content: flex-end;
}

.split-groups__summary {
	margin: 0;
}

.split-groups__summary-card {
	background: var(--pos-surface-raised);
	border: 1px solid rgba(0, 0, 0, 0.06);
	border-radius: var(--pos-radius-md);
	padding: 14px 16px;
}

.split-groups__summary-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
}

.split-groups__summary-label {
	font-weight: 700;
}

.split-groups__summary-value {
	font-weight: 700;
}

.split-groups__summary-meta {
	margin-top: 6px;
	color: var(--pos-text-secondary);
	font-size: 0.85rem;
}

.split-groups__list {
	display: flex;
	flex-direction: column;
	gap: 14px;
}

.split-groups__group {
	background: var(--pos-surface-raised);
	border: 1px solid rgba(0, 0, 0, 0.06);
	border-radius: var(--pos-radius-md);
	padding: 14px;
}

.split-groups__group-head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 12px;
	margin-bottom: 10px;
}

.split-groups__group-title {
	font-size: 1rem;
	font-weight: 700;
}

.split-groups__items {
	display: flex;
	flex-direction: column;
	gap: 10px;
}

.split-groups__item {
	display: grid;
	grid-template-columns: minmax(0, 1fr) minmax(220px, 280px);
	gap: 12px;
	align-items: center;
	padding: 12px;
	border-radius: var(--pos-radius-sm);
	background: rgba(0, 0, 0, 0.02);
}

.split-groups__item-name {
	font-weight: 600;
}

.split-groups__item-meta {
	color: var(--pos-text-secondary);
	font-size: 0.84rem;
	margin-top: 4px;
}

.split-groups__item-actions {
	display: grid;
	grid-template-columns: auto minmax(150px, 1fr);
	gap: 10px;
	align-items: center;
}

.split-groups__item-total {
	font-weight: 700;
	text-align: right;
}

.split-groups__empty {
	color: var(--pos-text-secondary);
	font-size: 0.9rem;
	padding: 8px 2px 2px;
}

@media (max-width: 768px) {
	.split-groups__item,
	.split-groups__item-actions {
		grid-template-columns: 1fr;
	}

	.split-groups__group-head {
		align-items: stretch;
		flex-direction: column;
	}

	.split-groups__item-total {
		text-align: left;
	}
}
</style>
