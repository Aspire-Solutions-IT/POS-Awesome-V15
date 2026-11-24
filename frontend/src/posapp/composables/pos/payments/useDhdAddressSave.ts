// Orchestrates saving a typed DHD delivery address and selecting it in the address picker.
//
// A save is "pending" from the moment Save is pressed until the new address is the one selected
// (shipping_address_name / customer_address). One generation covers the POST *and* the picker
// reload: every event that makes the save irrelevant (a newer save, a form reset, another
// customer/charge/invoice, the cashier picking another address, unmount) calls `abandon()`, so a
// late result is dropped instead of applied. While pending the previous selection is cleared and
// checkout progression is blocked.
import { ref, type Ref } from "vue";
import type { AddressLoadResult } from "../invoice/useInvoiceDetails";
import type { DhdSaveSettlement } from "../../../services/orderAddressService";

type SavedPayload = {
	saveId?: number;
	name?: string;
	customer?: string;
	deliveryCharge?: string;
	settle?: (result: DhdSaveSettlement) => void;
};

export type DhdAddressSaveDeps = {
	getDoc: () => any;
	/** The name of the delivery charge currently selected. */
	getCharge: () => string;
	isDhdChargeSelected: () => boolean;
	getAddresses: (options: { select?: string; isStillWanted?: () => boolean }) => Promise<AddressLoadResult>;
	invalidateAddressRequests: () => void;
	addresses: Ref<any[]>;
	normalizeAddress: (address: any) => any;
	clearStoreCollectionSelection: () => void;
	notify: (title: string, color: "error" | "warning") => void;
	translate?: (text: string) => string;
};

export function useDhdAddressSave(deps: DhdAddressSaveDeps) {
	const __ = deps.translate || ((text: string) => text);
	const pending = ref(false);
	let generation = 0;
	let activeSaveId: number | null = null;
	let activeSettle: ((result: DhdSaveSettlement) => void) | null = null;
	let previousSelection: { shipping: string | null; address: string | null; customer: string } | null = null;

	const finish = () => {
		pending.value = false;
		activeSaveId = null;
		activeSettle = null;
		previousSelection = null;
	};

	/** Drop whatever save is in flight; its form is told it was superseded. */
	const abandon = () => {
		generation += 1;
		const settle = activeSettle;
		finish();
		settle?.({ status: "superseded" });
	};

	/** True (after telling the cashier) while an address save is still in flight. */
	const blockWhilePending = (): boolean => {
		if (!pending.value) {
			return false;
		}
		deps.notify(__("The delivery address is still being saved. Wait for it to finish."), "warning");
		return true;
	};

	const onSaving = (info?: { saveId?: number }) => {
		abandon();
		const doc = deps.getDoc();
		if (!doc) {
			return;
		}
		activeSaveId = info?.saveId ?? null;
		pending.value = true;
		previousSelection = {
			shipping: doc.shipping_address_name || null,
			address: doc.customer_address || null,
			customer: String(doc.customer || ""),
		};
		// The previous selection must not stand in for the address being saved.
		deps.invalidateAddressRequests();
		doc.shipping_address_name = null;
		doc.customer_address = null;
		deps.clearStoreCollectionSelection();
	};

	/** The POST failed, or the form cancelled the save (edit, reset, unmount). */
	const onSaveEnded = (info?: { saveId?: number; reason?: string }) => {
		if (!info || info.saveId !== activeSaveId) {
			return;
		}
		const previous = previousSelection;
		abandon();
		const doc = deps.getDoc();
		// Nothing was saved, so the address picked before is still a valid choice.
		if (
			info.reason === "failed" &&
			previous?.shipping &&
			doc &&
			String(doc.customer || "") === previous.customer &&
			!String(doc.shipping_address_name || "").trim()
		) {
			doc.shipping_address_name = previous.shipping;
			doc.customer_address = previous.address;
		}
	};

	const onSaved = async (saved: SavedPayload) => {
		const settle = typeof saved?.settle === "function" ? saved.settle : () => {};
		const name = String(saved?.name || "").trim();
		if (!name) {
			settle({ status: "failed" });
			abandon();
			return;
		}
		if (!deps.getDoc() || saved.saveId !== activeSaveId) {
			settle({ status: "superseded" });
			return;
		}
		activeSettle = settle;
		const myGeneration = generation;
		// Nothing has abandoned this save, and the customer and (DHD) charge it was saved for are
		// still the ones selected.
		const isStillCurrent = () =>
			myGeneration === generation &&
			String(saved.customer || "") === String(deps.getDoc()?.customer || "") &&
			String(saved.deliveryCharge || "") === String(deps.getCharge() || "").trim() &&
			deps.isDhdChargeSelected();
		const dropIfNotCurrent = () => {
			if (isStillCurrent()) {
				return false;
			}
			// An abandoned save was settled already; settle one that merely stopped matching.
			if (myGeneration === generation) {
				abandon();
			}
			return true;
		};
		if (dropIfNotCurrent()) {
			return;
		}
		// Reload the picker and select the saved row by name. A reload that a plain list request
		// overtook is repeated once; a superseded result never reaches the fallback below.
		let outcome: AddressLoadResult = "superseded";
		for (let attempt = 0; attempt < 2 && outcome === "superseded"; attempt += 1) {
			deps.invalidateAddressRequests();
			outcome = await deps.getAddresses({ select: name, isStillWanted: isStillCurrent });
			if (dropIfNotCurrent()) {
				return;
			}
		}
		const confirmed = () => String(deps.getDoc()?.shipping_address_name || "").trim() === name;
		if (outcome === "applied" && confirmed()) {
			finish();
			settle({ status: "confirmed" });
			return;
		}
		// The list could not confirm the row, but the server named a persisted address: select it by
		// name. Only the server's own data is shown, never what was typed.
		try {
			const doc = deps.getDoc();
			const existing = (Array.isArray(deps.addresses.value) ? deps.addresses.value : []).filter(
				(addr) => addr.name !== name,
			);
			deps.addresses.value = [...existing, deps.normalizeAddress({ name })];
			doc.shipping_address_name = name;
			doc.customer_address = name;
			if (!confirmed()) {
				throw new Error("address selection was not applied");
			}
		} catch (error) {
			console.error("Failed to select the saved DHD address", error);
			finish();
			deps.notify(__("The address was saved but could not be selected. Press Retry."), "error");
			settle({ status: "failed" });
			return;
		}
		finish();
		settle({ status: "confirmed" });
	};

	return { pending, abandon, blockWhilePending, onSaving, onSaved, onSaveEnded };
}
