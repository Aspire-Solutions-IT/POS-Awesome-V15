<template>
	<v-dialog
		:model-value="modelValue"
		max-width="560"
		scrollable
		@update:model-value="emit('update:modelValue', $event)"
	>
		<v-card class="pos-themed-card delivery-estimate">
			<v-card-text class="pa-6">
				<div class="delivery-estimate__window">
					<div class="delivery-estimate__window-label">
						{{ __("Estimated Delivery (if submitted now)") }}
					</div>
					<div v-if="estimate?.window" class="delivery-estimate__window-value" data-test="estimate-window">
						{{ estimate.window }}
					</div>
					<div v-else class="delivery-estimate__window-pending">
						{{ emptyMessage }}
					</div>
				</div>

				<v-table v-if="estimate?.lines?.length" density="compact" class="delivery-estimate__lines mt-4">
					<thead>
						<tr>
							<th>{{ __("Item") }}</th>
							<th class="text-right">{{ __("Qty") }}</th>
							<th>{{ __("Supply") }}</th>
							<th>{{ __("Quoted Date") }}</th>
						</tr>
					</thead>
					<tbody>
						<tr v-for="(line, idx) in estimate.lines" :key="`${line.item_code}-${idx}`">
							<td>{{ line.item_name || line.item_code }}</td>
							<td class="text-right">{{ line.qty }}</td>
							<td>{{ __(line.source) }}</td>
							<td>{{ formatDate(line.quoted_date) }}</td>
						</tr>
					</tbody>
				</v-table>

				<div class="delivery-estimate__note mt-4">
					{{ __("Estimate only — stock and incoming supply can change before the order is submitted.") }}
				</div>
			</v-card-text>
			<v-card-actions class="px-6 pb-4">
				<v-spacer />
				<v-btn color="primary" variant="tonal" @click="emit('update:modelValue', false)">
					{{ __("Close") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
	modelValue: Boolean,
	estimate: {
		type: Object,
		default: null,
	},
});

const emit = defineEmits(["update:modelValue"]);

const __ = window.__;

const emptyMessage = computed(() => __("No delivery window could be estimated for this cart."));

function formatDate(value) {
	if (!value) {
		return "—";
	}
	const [year, month, day] = String(value).slice(0, 10).split("-");
	return year && month && day ? `${day}-${month}-${year}` : value;
}
</script>

<style scoped>
.delivery-estimate__window {
	padding: 14px 16px;
	border-radius: 8px;
	background: rgba(var(--v-theme-primary), 0.08);
}

.delivery-estimate__window-label {
	font-size: 0.75rem;
	text-transform: uppercase;
	letter-spacing: 0.08em;
	opacity: 0.7;
}

.delivery-estimate__window-value {
	margin-top: 4px;
	font-size: 1.4rem;
	font-weight: 600;
}

.delivery-estimate__window-pending {
	margin-top: 6px;
	font-size: 0.9rem;
	opacity: 0.75;
}

.delivery-estimate__note {
	font-size: 0.8rem;
	opacity: 0.7;
}
</style>
