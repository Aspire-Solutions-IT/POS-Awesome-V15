<template>
	<v-dialog
		:model-value="modelValue"
		max-width="430"
		persistent
		transition="dialog-bottom-transition"
		:retain-focus="false"
		@update:model-value="$emit('update:modelValue', $event)"
	>
		<v-card>
			<v-card-title class="text-h6 text-primary">
				{{ __("Has the customer taken away?") }}
			</v-card-title>
			<v-card-text class="text-body-2">
				{{
					__(
						"You have not entered an address. This will mark the order as taken on the day. Are you sure?",
					)
				}}
			</v-card-text>
			<v-card-actions>
				<v-spacer></v-spacer>
				<v-btn ref="customerCollectedBtn" color="success" variant="flat" @click="onCustomerCollected">
					{{ __("Customer Collected") }}
				</v-btn>
				<v-btn color="primary" variant="text" @click="onEnterAddress">
					{{ __("Enter Address") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup>
import { nextTick, ref, watch } from "vue";

defineOptions({
	name: "MissingOrderAddressDialog",
});

const props = defineProps({
	modelValue: Boolean,
});

const emit = defineEmits(["update:modelValue", "customer-collected", "enter-address"]);

const __ = window.__ || ((text) => text);
const customerCollectedBtn = ref(null);

const focus = () => {
	nextTick(() => {
		setTimeout(() => {
			customerCollectedBtn.value?.$el?.focus();
		}, 100);
	});
};

watch(
	() => props.modelValue,
	(val) => {
		if (val) {
			focus();
		}
	},
);

const onCustomerCollected = () => {
	emit("customer-collected");
};

const onEnterAddress = () => {
	emit("enter-address");
};
</script>
