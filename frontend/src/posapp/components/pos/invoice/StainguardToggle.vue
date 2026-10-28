<template>
	<div v-if="available" class="stainguard-toggle" data-test="stainguard-toggle-root">
		<div class="stainguard-toggle__row">
			<v-checkbox
				:model-value="modelValue"
				:label="__('Add stainguard')"
				color="primary"
				density="compact"
				hide-details
				data-test="stainguard-toggle"
				@update:model-value="emit('update:modelValue', Boolean($event))"
			/>
			<img
				class="stainguard-toggle__logo"
				:src="LOGO_URL"
				:alt="__('Stainguard')"
				height="28"
				data-test="stainguard-logo"
			/>
		</div>
		<div v-if="modelValue" class="stainguard-toggle__detail" data-test="stainguard-detail">
			<v-progress-circular v-if="status.loading" indeterminate size="14" width="2" />
			<span v-else-if="status.message" class="stainguard-toggle__message">{{ status.message }}</span>
			<span v-else-if="status.item_name">
				{{ status.item_name }} -
				<strong data-test="stainguard-price">{{ priceLabel }}</strong>
			</span>
		</div>
	</div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
	// Whether this cart can carry Stainguard cover (profile enabled, Sales Order).
	available: Boolean,
	modelValue: Boolean,
	// { loading, item_name, rate, message } for the cover currently in the cart.
	status: {
		type: Object,
		default: () => ({ loading: false, item_name: "", rate: 0, message: "" }),
	},
	formatCurrency: {
		type: Function,
		default: null,
	},
});

const emit = defineEmits(["update:modelValue"]);

const __ = window.__;

// Served from the app's public folder; bound rather than written inline so the
// bundler leaves the runtime URL alone.
const LOGO_URL = "/assets/posawesome/images/stainguard-logo.jpg";

const priceLabel = computed(() => {
	const rate = Number(props.status?.rate || 0);
	return props.formatCurrency ? props.formatCurrency(rate) : rate.toFixed(2);
});
</script>

<style scoped>
.stainguard-toggle {
	display: flex;
	flex-direction: column;
	gap: 2px;
	width: 100%;
}

.stainguard-toggle__row {
	display: flex;
	align-items: center;
	gap: 6px;
}

.stainguard-toggle__logo {
	height: 28px;
	width: auto;
	border-radius: 4px;
	flex: none;
}

.stainguard-toggle__detail {
	min-height: 18px;
	padding-left: 38px;
	font-size: 0.8rem;
	opacity: 0.8;
}

.stainguard-toggle__message {
	font-style: italic;
}
</style>
