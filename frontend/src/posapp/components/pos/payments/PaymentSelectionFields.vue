<template>
	<div class="selection-fields">
		<!-- Print Format Selection -->
		<v-row v-if="showPrintFormat" class="pb-0 mb-2" align="start">
			<v-col cols="12">
				<v-select
					density="compact"
					clearable
					variant="solo"
					color="primary"
					:label="$frappe._('Print Format')"
					:model-value="printFormat"
					:items="printFormats"
					class="sleek-field pos-themed-input"
					:no-data-text="$__('No Print Formats Found')"
					hide-details
					@update:model-value="$emit('update:print-format', $event)"
				></v-select>
			</v-col>
		</v-row>
	</div>
</template>

<script setup>
import { inject } from "vue";

defineProps({
	printFormats: {
		type: Array,
		default: () => [],
	},
	printFormat: {
		type: String,
		default: "",
	},
	showPrintFormat: {
		type: Boolean,
		default: true,
	},
});

defineEmits(["update:print-format"]);

const $frappe = inject("frappe", window.frappe);
const $__ = inject("__", window.__);
</script>

<style scoped>
.pos-themed-input :deep(.v-field__input) {
	font-weight: 500;
}
</style>
