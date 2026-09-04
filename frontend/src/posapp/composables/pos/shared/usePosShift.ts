import { ref, getCurrentInstance, inject } from "vue";
import { useToastStore } from "../../../stores/toastStore.js";
import { useUIStore } from "../../../stores/uiStore.js";
import { useEmployeeStore } from "../../../stores/employeeStore";
import {
	initPromise,
	checkDbHealth,
	getOpeningStorage,
	setOpeningStorage,
	clearOpeningStorage,
	setTaxTemplate,
	isOffline,
	getBootstrapSnapshot,
	setBootstrapSnapshot,
	getPendingOfflineInvoiceCount,
} from "../../../../offline/index";
import {
	clearActiveOpeningShiftName,
	getActiveOpeningShiftName,
	getValidCachedOpeningForCurrentUser,
	setActiveOpeningShiftName,
} from "../../../utils/openingCache";
import { createBootstrapSnapshotFromRegisterData } from "../../../../offline/bootstrapSnapshot";

declare const __BUILD_VERSION__: string;
declare const frappe: any;

type SkippedPrintedInvoice = {
	invoice?: string;
	doctype?: string;
	return_against?: string;
};

type ClosingShiftPreparationResponse = {
	closing_shift?: any;
	skipped_printed_invoices?: SkippedPrintedInvoice[];
};

const translateMessage = (value: string) => (typeof window !== "undefined" && window.__
	? window.__(value)
	: value);

/**
 * Full reload is how this app re-scopes the register. The POS Profile is baked into
 * the item cache scope, offline sync signatures, customer scope and a boot-only
 * uiStore, so a reload is cheaper to get right than a live re-scope.
 */
export function reloadTerminal(delayMs = 0) {
	const reload = () => {
		try {
			window.location.reload();
		} catch (e) {
			console.error("Failed to reload terminal", e);
		}
	};
	if (delayMs > 0) {
		setTimeout(reload, delayMs);
		return;
	}
	reload();
}

export function buildSkippedClosingInvoicesPrompt(
	skippedInvoices: SkippedPrintedInvoice[],
) {
	const count = skippedInvoices.length;
	const baseMessage = count === 1
		? "1 printed return invoice references a cancelled invoice and will be excluded from closing."
		: `${count} printed return invoices reference cancelled invoices and will be excluded from closing.`;
	const details = skippedInvoices
		.slice(0, 5)
		.map((invoice) => {
			const invoiceName = invoice?.invoice || translateMessage("Unknown invoice");
			const returnAgainst = invoice?.return_against;
			return returnAgainst
				? `${invoiceName} (${translateMessage("Return Against")}: ${returnAgainst})`
				: invoiceName;
		})
		.join(", ");
	const detailMessage = details
		? `${translateMessage("Invoices")}: ${details}.`
		: "";
	return [
		translateMessage(baseMessage),
		detailMessage,
		translateMessage("The skipped invoice will remain a draft."),
		translateMessage("Do you want to proceed?"),
	]
		.filter(Boolean)
		.join(" ");
}

function normalizeClosingShiftPreparationResponse(
	payload: any,
): ClosingShiftPreparationResponse {
	if (payload?.closing_shift || payload?.skipped_printed_invoices) {
		return payload;
	}

	return {
		closing_shift: payload,
		skipped_printed_invoices: [],
	};
}

export function usePosShift(openDialog?: () => void) {
	const instance = getCurrentInstance();
	const proxy: any = instance?.proxy;
	const eventBus: any = proxy?.eventBus || inject("eventBus");
	const buildVersion =
		typeof __BUILD_VERSION__ !== "undefined" ? __BUILD_VERSION__ : null;
	const toastStore = useToastStore();
	const uiStore = useUIStore();
	const employeeStore = useEmployeeStore();

	const pos_profile = ref<any>(null);
	const pos_opening_shift = ref<any>(null);

	function applyRegisterData(data: any) {
		if (!data) {
			return;
		}
		pos_profile.value = data.pos_profile;
		pos_opening_shift.value = data.pos_opening_shift;
		uiStore.setRegisterData(data);
		setActiveOpeningShiftName(data.pos_opening_shift?.name);
		setBootstrapSnapshot(
			createBootstrapSnapshotFromRegisterData(
				data,
				getBootstrapSnapshot(),
				{ buildVersion },
			),
		);

		try {
			frappe.realtime.emit("pos_profile_registered");
		} catch (e) {
			console.warn("Realtime emit failed", e);
		}

		// Always require a cashier PIN unlock after the opening balance is
		// confirmed, rather than silently continuing as the logged-in browser user.
		employeeStore.lockTerminal();
	}

	async function check_opening_entry() {
		await initPromise;
		await checkDbHealth();
		const cachedOpening = getValidCachedOpeningForCurrentUser(
			getOpeningStorage(),
			frappe?.session?.user,
		);
		if (cachedOpening) {
			applyRegisterData(cachedOpening);
			console.info("LoadPosProfile (bootstrapped from cache)");
		}
		return frappe
			.call("posawesome.posawesome.api.shifts.check_opening_shift", {
				user: frappe.session.user,
				preferred_shift: getActiveOpeningShiftName() || null,
			})
			.then((r: any) => {
				if (r.message) {
					applyRegisterData(r.message);
					if (pos_profile.value.taxes_and_charges) {
						frappe.call({
							method: "frappe.client.get",
							args: {
								doctype: "Sales Taxes and Charges Template",
								name: pos_profile.value.taxes_and_charges,
							},
							callback: (res: any) => {
								if (res.message) {
									setTaxTemplate(
										pos_profile.value.taxes_and_charges,
										res.message,
									);
								}
							},
						});
					}
					console.info("LoadPosProfile");
					try {
						setOpeningStorage(r.message);
					} catch (e) {
						console.error("Failed to cache opening data", e);
					}
				} else {
					console.info("No opening shift found, opening dialog");
					clearActiveOpeningShiftName();
					clearOpeningStorage();
					openDialog && openDialog();
				}
			})
			.catch((err: unknown) => {
				console.error("Error checking opening entry", err);
				const data = cachedOpening ||
					getValidCachedOpeningForCurrentUser(
						getOpeningStorage(),
						frappe?.session?.user,
					);
				if (data) {
					applyRegisterData(data);
					console.info("LoadPosProfile (cached)");
					return;
				}
				if (!isOffline()) {
					clearActiveOpeningShiftName();
					clearOpeningStorage();
				}
				openDialog && openDialog();
			});
	}

	function get_closing_data() {
		const cachedOpeningShift = (getOpeningStorage() as any)
			?.pos_opening_shift;
		if (!pos_opening_shift.value && cachedOpeningShift) {
			pos_opening_shift.value = cachedOpeningShift;
		}
		if (!pos_opening_shift.value) {
			return Promise.resolve();
		}
		return frappe
			.call(
				"posawesome.posawesome.doctype.pos_closing_shift.pos_closing_shift.make_closing_shift_from_opening",
				{ opening_shift: pos_opening_shift.value },
			)
			.then((r: any) => {
				if (r.message) {
					const response = normalizeClosingShiftPreparationResponse(r.message);
					const closingShift = response.closing_shift;
					const skippedPrintedInvoices = Array.isArray(response.skipped_printed_invoices)
						? response.skipped_printed_invoices
						: [];
					if (!closingShift) {
						return;
					}

					if (skippedPrintedInvoices.length) {
						const confirmed = window.confirm(
							buildSkippedClosingInvoicesPrompt(skippedPrintedInvoices),
						);
						if (!confirmed) {
							return;
						}
					}

					eventBus?.emit("open_ClosingDialog", closingShift);
				}
			});
	}

	/**
	 * Move this terminal to another POS Profile without closing the current shift.
	 *
	 * The outgoing shift stays open server-side, so its invoices keep their own
	 * reconciliation. Once the server hands back the new register payload we prime the
	 * offline caches and reload: the profile is baked into the item cache scope, the
	 * sync adapter signatures and the customer scope, and `ItemsSelector` refuses to
	 * re-initialise once booted, so a reload is what actually re-scopes the terminal.
	 */
	async function switch_pos_profile(payload: {
		target_profile: string;
		balance_details?: any[];
		supervisor_user?: string;
		pin?: string;
	}) {
		if (isOffline()) {
			toastStore.show({
				title: translateMessage("Go online to switch POS profile."),
				color: "error",
			});
			return { success: false, reason: "offline" };
		}

		if (getPendingOfflineInvoiceCount() > 0) {
			toastStore.show({
				title: translateMessage(
					"Sync pending offline sales before switching POS profile.",
				),
				color: "error",
			});
			return { success: false, reason: "pending_invoices" };
		}

		const currentProfileName =
			uiStore.posProfile?.name || pos_profile.value?.name || null;

		try {
			const r = await frappe.call(
				"posawesome.posawesome.api.shifts.switch_pos_profile",
				{
					target_profile: payload.target_profile,
					current_profile: currentProfileName,
					balance_details: JSON.stringify(payload.balance_details || []),
					supervisor_user: payload.supervisor_user || null,
					pin: payload.pin || null,
				},
			);

			if (!r?.message) {
				return { success: false, reason: "empty_response" };
			}

			setOpeningStorage(r.message);
			setActiveOpeningShiftName(r.message?.pos_opening_shift?.name);
			setBootstrapSnapshot(
				createBootstrapSnapshotFromRegisterData(
					r.message,
					getBootstrapSnapshot(),
					{ buildVersion },
				),
			);

			reloadTerminal();
			return { success: true, register_data: r.message };
		} catch (err: any) {
			console.error("Failed to switch POS profile", err);
			return { success: false, reason: "error", error: err };
		}
	}

	function submit_closing_pos(data: any) {
		console.log("Submitting closing shift", data);
		frappe
			.call(
				"posawesome.posawesome.doctype.pos_closing_shift.pos_closing_shift.submit_closing_shift",
				{
					closing_shift: JSON.stringify(data),
				},
			)
			.then((r: any) => {
				console.log("Submit result", r);
				if (r.message) {
					pos_profile.value = null;
					pos_opening_shift.value = null;
					clearActiveOpeningShiftName();
					clearOpeningStorage();
					toastStore.show({
						title: "POS Shift Closed",
						color: "success",
					});
					// The cashier may still hold an open shift on another profile. Reload
					// rather than re-checking in place: uiStore cannot clear the outgoing
					// profile and ItemsSelector will not re-scope without a fresh boot.
					// Short delay so the confirmation toast is actually readable.
					reloadTerminal(1200);
				}
			})
			.catch((err: unknown) => {
				console.error("Failed to submit closing shift", err);
			});
	}

	return {
		pos_profile,
		pos_opening_shift,
		check_opening_entry,
		get_closing_data,
		submit_closing_pos,
		switch_pos_profile,
	};
}
