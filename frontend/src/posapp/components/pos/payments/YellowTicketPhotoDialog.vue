<template>
	<v-dialog
		:model-value="gate.dialogOpen.value"
		max-width="640"
		persistent
		scrollable
		:retain-focus="false"
	>
		<v-card>
			<v-card-title class="text-h6 text-primary d-flex align-center">
				<v-icon class="mr-2">mdi-camera</v-icon>
				{{ __("Yellow Ticket photos") }}
			</v-card-title>
			<v-card-subtitle class="text-wrap">
				{{
					__("Add the minimum number of photos shown for each item below before taking payment.")
				}}
			</v-card-subtitle>

			<v-card-text>
				<v-alert v-if="owedConfirmOpen" type="warning" variant="tonal" class="mb-4">
					{{
						__(
							"The till is offline, so photos can't be added from a phone either. Complete the sale and record its Yellow Ticket photos as owed?",
						)
					}}
					<div class="mt-2">
						<v-btn color="warning" variant="flat" size="small" class="mr-2" @click="gate.markPhotosOwed()">
							{{ __("Complete sale, photos owed") }}
						</v-btn>
						<v-btn variant="text" size="small" @click="owedConfirmOpen = false">{{ __("Back") }}</v-btn>
					</div>
				</v-alert>
				<div v-if="phoneLink" class="yt-phone mb-4">
					<img :src="phoneLink.qr" :alt="__('QR code for adding photos from a phone')" class="yt-qr" />
					<div class="text-body-2">
						<p class="mb-1">{{ __("Scan this with a phone camera to take the photos on the phone.") }}</p>
						<p class="mb-1 text-medium-emphasis">
							{{ __("The counts below update as photos arrive.") }}
						</p>
						<v-btn size="small" variant="text" @click="phoneLink = null">{{ __("Hide QR code") }}</v-btn>
					</div>
				</div>

				<div
					v-for="line in gate.lines.value"
					:key="line.row_ref"
					class="yt-line"
					:class="{ 'yt-line--done': store.count(line.row_ref) >= gate.minimumPhotos(line) }"
				>
					<div class="d-flex align-center">
						<div class="flex-grow-1">
							<div class="font-weight-medium">{{ line.item_name }}</div>
							<div class="text-caption text-medium-emphasis">
								{{ line.item_code }} · {{ __("Qty") }} {{ line.qty }}
							</div>
						</div>
						<v-chip
							size="small"
							:color="store.count(line.row_ref) >= gate.minimumPhotos(line) ? 'success' : 'warning'"
						>
							{{ store.count(line.row_ref) }} / {{ gate.minimumPhotos(line) }}
						</v-chip>
					</div>

					<div class="yt-thumbs">
						<img
							v-for="photo in store.photos[line.row_ref] || []"
							:key="photo.client_photo_ref"
							:src="photo.data_url"
							class="yt-thumb"
							alt=""
						/>
						<span v-if="store.serverCounts.phone[line.row_ref]" class="text-caption text-medium-emphasis">
							{{ __("+{0} from phone", [store.serverCounts.phone[line.row_ref]]) }}
						</span>
					</div>

					<v-btn
						color="primary"
						variant="tonal"
						size="small"
						prepend-icon="mdi-camera"
						:loading="busyRow === line.row_ref"
						:disabled="store.count(line.row_ref) >= gate.config.value.max_photos"
						@click="pickPhoto(line)"
					>
						{{ __("Take photo") }}
					</v-btn>
				</div>

				<input
					ref="fileInput"
					type="file"
					accept="image/*"
					capture="environment"
					multiple
					class="d-none"
					@change="onFilesChosen"
				/>
			</v-card-text>

			<v-card-actions class="flex-wrap">
				<v-btn
					v-if="online"
					variant="text"
					prepend-icon="mdi-cellphone"
					:loading="phoneLoading"
					@click="showPhoneLink"
				>
					{{ __("Use a phone") }}
				</v-btn>
				<v-btn
					v-else-if="!gate.isComplete()"
					variant="text"
					color="warning"
					prepend-icon="mdi-camera-off"
					@click="owedConfirmOpen = true"
				>
					{{ __("Camera not working") }}
				</v-btn>
				<v-spacer></v-spacer>
				<v-btn variant="text" @click="gate.cancel()">{{ __("Cancel") }}</v-btn>
				<v-btn color="success" variant="flat" :disabled="!gate.isComplete()" @click="gate.continueSale()">
					{{ __("Continue") }}
				</v-btn>
			</v-card-actions>
		</v-card>
	</v-dialog>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";

import { isOffline } from "../../../../offline/index";
import { useYellowTicketPhotoGate } from "../../../composables/pos/payments/useYellowTicketPhotoGate";
import { useToastStore } from "../../../stores/toastStore.js";
import { useYellowTicketPhotoStore } from "../../../stores/yellowTicketPhotoStore";
import type { YellowTicketLine } from "../../../utils/yellowTicketPhotos";

defineOptions({ name: "YellowTicketPhotoDialog" });

const __ = (window as any).__ || ((text: string) => text);
const gate = useYellowTicketPhotoGate();
const store = useYellowTicketPhotoStore();
const toastStore = useToastStore();

const POLL_MS = 3000;
const fileInput = ref<HTMLInputElement | null>(null);
const pendingLine = ref<YellowTicketLine | null>(null);
const busyRow = ref("");
const online = ref(!isOffline());
const phoneLink = ref<{ url: string; qr: string } | null>(null);
const phoneLoading = ref(false);
const owedConfirmOpen = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

const poll = () => {
	online.value = !isOffline();
	if (online.value && gate.posProfileName.value) {
		void store.refreshServerCounts(gate.posProfileName.value).catch(() => undefined);
	}
};

watch(
	() => gate.dialogOpen.value,
	(open) => {
		if (pollTimer) clearInterval(pollTimer);
		pollTimer = null;
		if (open) {
			phoneLink.value = null;
			owedConfirmOpen.value = false;
			online.value = !isOffline();
			pollTimer = setInterval(poll, POLL_MS);
		}
	},
);

onBeforeUnmount(() => {
	if (pollTimer) clearInterval(pollTimer);
});

const pickPhoto = (line: YellowTicketLine) => {
	pendingLine.value = line;
	fileInput.value?.click();
};

const onFilesChosen = async (event: Event) => {
	const input = event.target as HTMLInputElement;
	const files = Array.from(input.files || []);
	input.value = "";
	const line = pendingLine.value;
	if (!line || !files.length) return;
	busyRow.value = line.row_ref;
	try {
		for (const file of files) {
			if (store.count(line.row_ref) >= gate.config.value.max_photos) break;
			await store.addPhoto(file, line, gate.posProfileName.value, gate.cashier.value);
		}
	} catch (error) {
		console.error("Yellow Ticket photo could not be saved", error);
		toastStore.show({ title: __("That photo could not be saved. Try again."), color: "error" });
	} finally {
		busyRow.value = "";
	}
};

const showPhoneLink = async () => {
	phoneLoading.value = true;
	try {
		phoneLink.value = await store.requestPhoneLink(
			gate.posProfileName.value,
			gate.lines.value,
			gate.cashier.value,
		);
	} catch (error: any) {
		toastStore.show({
			title: __("Could not create the phone link"),
			detail: error?.message || "",
			color: "error",
		});
	} finally {
		phoneLoading.value = false;
	}
};
</script>

<style scoped>
.yt-line {
	border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
	border-radius: 8px;
	padding: 12px;
	margin-bottom: 12px;
}
.yt-line--done {
	border-color: rgb(var(--v-theme-success));
}
.yt-thumbs {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 6px;
	margin: 8px 0;
	min-height: 8px;
}
.yt-thumb {
	width: 56px;
	height: 56px;
	object-fit: cover;
	border-radius: 4px;
}
.yt-phone {
	display: flex;
	gap: 16px;
	align-items: center;
}
.yt-qr {
	width: 180px;
	height: 180px;
	image-rendering: pixelated;
}
</style>
