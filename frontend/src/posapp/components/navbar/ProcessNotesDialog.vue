<template>
	<v-dialog v-model="dialogModel" max-width="560">
		<v-card class="pos-themed-card">
			<v-card-title class="d-flex align-center">
				<v-icon start color="primary">mdi-file-document-multiple-outline</v-icon>
				{{ __("Process Documents") }}
			</v-card-title>
			<v-card-subtitle v-if="screen">{{ __(screen) }}</v-card-subtitle>

			<v-card-text>
				<v-list density="comfortable" lines="two">
					<v-list-item
						v-for="note in notes"
						:key="note.name"
						:href="note.url"
						target="_blank"
						rel="noopener noreferrer"
						:data-test="`process-note-${note.name}`"
					>
						<v-list-item-title class="d-flex align-center">
							<span>{{ note.title }}</span>
							<v-chip v-if="note.category" size="x-small" class="ml-2">
								{{ note.category }}
							</v-chip>
						</v-list-item-title>
						<v-list-item-subtitle v-if="note.description">
							{{ note.description }}
						</v-list-item-subtitle>
						<template #append>
							<v-icon size="18">mdi-open-in-new</v-icon>
						</template>
					</v-list-item>
				</v-list>
			</v-card-text>

			<v-card-actions class="pa-4 pt-0">
				<v-spacer />
				<v-btn color="grey" variant="text" @click="dialogModel = false">
					{{ __("Close") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script>
export default {
	name: "ProcessNotesDialog",
	props: {
		modelValue: Boolean,
		notes: { type: Array, default: () => [] },
		screen: { type: String, default: "" },
	},
	emits: ["update:modelValue"],
	computed: {
		dialogModel: {
			get() {
				return this.modelValue;
			},
			set(value) {
				this.$emit("update:modelValue", value);
			},
		},
	},
	methods: {
		__(text) {
			return window.__ ? window.__(text) : text;
		},
	},
};
</script>
