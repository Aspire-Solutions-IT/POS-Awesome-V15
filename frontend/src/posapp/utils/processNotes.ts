// Process notes (Zoho WorkDrive docs) linked to POS screens. The notes and
// their links are managed in customer_due_dates' Process Note DocType; the
// desk has its own client for them (customer_due_dates/public/js/process_notes.js).

declare const frappe: any;

export const PROCESS_NOTES_METHOD = "customer_due_dates.process_notes.api.get_process_notes";
export const PROCESS_NOTES_UPDATED_EVENT = "process_notes_updated";
export const ALL_POS_SCREENS = "All Screens";

// Must match the POS Screen options on Process Note Link. Each screen is
// identified by its router meta.title (see router/index.ts).
export const POS_SCREENS = [
	"POS",
	"Orders",
	"Payments",
	"Sales Orders",
	"Customer Claims",
	"Gift Cards",
	"Reports",
	"Barcode Printing",
	"Cash Movement",
	"Close Shift",
] as const;

export interface ProcessNoteLink {
	link_type: string;
	link_name?: string | null;
	show_on?: string | null;
	pos_screen?: string | null;
}

export interface ProcessNote {
	name: string;
	title: string;
	url: string;
	category?: string | null;
	description?: string | null;
	links: ProcessNoteLink[];
}

export function posScreenForRoute(route: any): string {
	const title = route?.meta?.title;
	return typeof title === "string" ? title : "";
}

export function notesForPosScreen(notes: ProcessNote[] | null | undefined, screen: string) {
	return (notes || []).filter((note) =>
		(note.links || []).some(
			(link) =>
				link.link_type === "POS Screen" &&
				(link.pos_screen === ALL_POS_SCREENS || (!!screen && link.pos_screen === screen)),
		),
	);
}

let cached: ProcessNote[] | null = null;
let inflight: Promise<ProcessNote[]> | null = null;

// Fetched once per page load. Failures (offline, or customer_due_dates not
// installed) resolve to no notes so the menu simply hides the entry.
export function loadProcessNotes(force = false): Promise<ProcessNote[]> {
	if (force) cached = null;
	if (cached) return Promise.resolve(cached);
	if (!inflight) {
		inflight = Promise.resolve()
			.then(() => frappe.call({ method: PROCESS_NOTES_METHOD }))
			.then((response: any) => {
				const notes = Array.isArray(response?.message) ? response.message : [];
				cached = notes;
				return notes;
			})
			.catch(() => [] as ProcessNote[])
			.finally(() => {
				inflight = null;
			});
	}
	return inflight;
}

// Returns an unsubscribe function.
export function onProcessNotesUpdated(callback: (_notes: ProcessNote[]) => void) {
	const realtime = typeof frappe !== "undefined" ? frappe?.realtime : null;
	if (!realtime?.on) return () => {};

	const handler = () => {
		void loadProcessNotes(true).then(callback);
	};
	realtime.on(PROCESS_NOTES_UPDATED_EVENT, handler);
	return () => realtime.off?.(PROCESS_NOTES_UPDATED_EVENT, handler);
}

export function resetProcessNotesCache() {
	cached = null;
	inflight = null;
}
