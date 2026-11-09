/**
 * Checkout gate for Yellow Ticket photos.
 *
 * `ensureYellowTicketPhotos` runs before payment opens and rechecks at submission. It
 * resolves to:
 * - `undefined` when no photos are needed (switched off, a return, no Yellow
 *   Ticket lines) -- the sale goes ahead unchanged;
 * - `false` when the cashier closed the photo dialog -- the sale is not submitted;
 * - the payload to send with the sale, once every line has enough photos or the
 *   till (offline) has marked the photos as owed.
 *
 * Both switches must be on: the POS Profile's "Require Yellow Ticket Photos" and
 * the site-wide setting, which the till caches for use offline. State is
 * module-level so the dialog component and Payments share it.
 */
import { ref } from "vue";

import { db, isOffline } from "../../../../offline/index";
import { startPhotoQueueFlusher } from "../../../../offline/yellowTicketPhotoQueue";
import { useYellowTicketPhotoStore } from "../../../stores/yellowTicketPhotoStore";
import {
	YT_REQUIREMENTS_METHOD,
	cacheConfig,
	cachedConfig,
	invoiceLines,
	isYellowTicketLine,
	minimumPhotosForItem,
	postMethod,
	type YellowTicketConfig,
	type YellowTicketLine,
	type YellowTicketSubmission,
} from "../../../utils/yellowTicketPhotos";

type AnyRecord = Record<string, any>;
type GateResult = YellowTicketSubmission | false | undefined;

const dialogOpen = ref(false);
const lines = ref<YellowTicketLine[]>([]);
const config = ref<YellowTicketConfig>({ enabled: false, min_photos: 3, max_photos: 10 });
const posProfileName = ref("");
const cashier = ref<string | undefined>(undefined);
let settle: ((result: GateResult) => void) | null = null;

async function offlineItems(codes: string[]): Promise<Record<string, AnyRecord>> {
	try {
		const rows = await db.table("items").bulkGet(codes);
		return Object.fromEntries(
			rows.filter(Boolean).map((row: AnyRecord) => [row.item_code, row]),
		);
	} catch {
		return {};
	}
}

async function requiredLines(profile: AnyRecord, doc: AnyRecord) {
	const all = invoiceLines(doc);
	if (!all.length) return null;

	if (!isOffline()) {
		try {
			const result = await postMethod<YellowTicketConfig & {
				row_refs: string[];
				min_photos_by_row?: Record<string, number>;
			}>(YT_REQUIREMENTS_METHOD, {
				pos_profile: profile.name,
				items: all,
			});
			const fresh = {
				enabled: Boolean(result?.enabled),
				min_photos: Number(result?.min_photos) || 3,
				max_photos: Number(result?.max_photos) || 10,
			};
			cacheConfig(profile.name, fresh);
			const wanted = new Set(result?.row_refs || []);
			return {
				config: fresh,
				lines: all.filter((line) => wanted.has(line.row_ref)).map((line) => ({
					...line,
					min_photos: result.min_photos_by_row?.[line.row_ref] ?? minimumPhotosForItem(line.item_code, fresh.min_photos),
				})),
			};
		} catch (error) {
			console.warn("Yellow Ticket photo requirements unavailable; using the cached settings", error);
		}
	}

	const cached = cachedConfig(profile.name);
	if (!cached?.enabled) return null;
	const items = await offlineItems(all.map((line) => line.item_code));
	return {
		config: cached,
		lines: all.filter((line: AnyRecord) =>
			isYellowTicketLine(
				line.item_code,
				line.item_group || items[line.item_code]?.item_group,
				items[line.item_code]?.is_staingard_item,
			),
		),
	};
}

export function useYellowTicketPhotoGate() {
	const store = useYellowTicketPhotoStore();

	const minimumPhotos = (line: YellowTicketLine) =>
		line.min_photos ?? minimumPhotosForItem(line.item_code, config.value.min_photos);

	const isComplete = () =>
		store.photosOwed || lines.value.every((line) => store.count(line.row_ref) >= minimumPhotos(line));

	const finish = (result: GateResult) => {
		dialogOpen.value = false;
		const done = settle;
		settle = null;
		done?.(result);
	};

	const ensureYellowTicketPhotos = async (
		profile: AnyRecord | null | undefined,
		doc: AnyRecord | null | undefined,
		invoiceType: string,
		currentCashier?: string,
	): Promise<GateResult> => {
		if (!profile?.posa_require_yellow_ticket_photos || !doc || doc.is_return || invoiceType === "Quotation") {
			return undefined;
		}
		// Already waiting on the dialog (e.g. the pay button pressed twice).
		if (dialogOpen.value) return false;
		startPhotoQueueFlusher();
		const requirement = await requiredLines(profile, doc);
		if (!requirement?.config.enabled || !requirement.lines.length) return undefined;

		config.value = requirement.config;
		lines.value = requirement.lines;
		posProfileName.value = profile.name;
		cashier.value = currentCashier;
		store.keepOnly(requirement.lines.map((line) => line.row_ref));
		if (!isOffline()) {
			await store.refreshServerCounts(profile.name).catch(() => undefined);
		}
		if (isComplete()) return store.submission(lines.value);

		dialogOpen.value = true;
		return new Promise<GateResult>((resolve) => {
			settle = resolve;
		});
	};

	/** Call once the sale has been submitted (or saved offline). */
	const completeSale = () => store.reset();

	return {
		dialogOpen,
		lines,
		config,
		posProfileName,
		cashier,
		minimumPhotos,
		isComplete,
		ensureYellowTicketPhotos,
		completeSale,
		continueSale: () => finish(store.submission(lines.value)),
		markPhotosOwed: () => {
			store.photosOwed = true;
			finish(store.submission(lines.value));
		},
		cancel: () => finish(false),
	};
}
