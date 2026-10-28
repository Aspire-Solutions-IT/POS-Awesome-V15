import api from "../../../services/api";
import { parseBooleanSetting } from "../../../utils/stock";

declare const __: (_text: string, _args?: any[]) => string;

/**
 * Stainguard Utils
 * Keeps the cart's Stainguard cover line in step with the cart.
 *
 * With "Add stainguard" ticked, the cart holds the Stainguard item whose
 * Starting/Top Value range covers the order total without its delivery charge
 * (and without the cover itself). As items come and go the line is swapped for
 * the right band, or removed when no item covers the order.
 *
 * Context requirements:
 * - context.invoiceType, context.isReturnInvoice, context.customer, context.items
 * - context.pos_profile (posa_enable_stainguard, name)
 * - context.subtotal, context.delivery_charges_rate, context.flt
 * - context.get_price_list, context.add_item, context.remove_item (methods)
 * - context.stainguard_enabled, context.stainguard_item_code, context.stainguard_status
 * - context.stainguard_signature (computed: the cart without the cover line)
 */

const SYNC_DELAY_MS = 400;

export interface StainguardStatus {
	loading: boolean;
	item_name: string;
	rate: number;
	message: string;
}

export const emptyStainguardStatus = (): StainguardStatus => ({
	loading: false,
	item_name: "",
	rate: 0,
	message: "",
});

/** Whether this cart can carry Stainguard cover at all. */
export function stainguardAvailable(context: any): boolean {
	return (
		context.invoiceType === "Order" &&
		!context.isReturnInvoice &&
		parseBooleanSetting(context.pos_profile?.posa_enable_stainguard)
	);
}

/** Re-sync shortly after the cart settles; bursts of edits cost one lookup. */
export function scheduleStainguardSync(context: any) {
	clearTimeout(context._stainguardTimer);
	context._stainguardTimer = setTimeout(() => {
		context._stainguardTimer = null;
		syncStainguard(context);
	}, SYNC_DELAY_MS);
}

/** Run any pending sync now and wait for it, so PAY sees the settled cart. */
export async function flushStainguardSync(context: any) {
	if (context._stainguardTimer) {
		clearTimeout(context._stainguardTimer);
		context._stainguardTimer = null;
		await syncStainguard(context);
	} else if (context._stainguardSync) {
		await context._stainguardSync;
	}
}

export function syncStainguard(context: any): Promise<void> {
	if (context._stainguardSync) {
		// A run is in flight; it loops again once it finishes.
		context._stainguardDirty = true;
		return context._stainguardSync;
	}

	context._stainguardSync = (async () => {
		try {
			do {
				context._stainguardDirty = false;
				await runSync(context);
			} while (context._stainguardDirty);
		} finally {
			context._stainguardSync = null;
		}
	})();
	return context._stainguardSync;
}

const cartLine = (context: any, itemCode: string) =>
	(context.items || []).filter((item: any) => item?.item_code === itemCode);

async function runSync(context: any) {
	const wanted = Boolean(
		stainguardAvailable(context) &&
			context.stainguard_enabled &&
			context.customer &&
			context.items.length,
	);

	if (!wanted) {
		// Ticked off, or the cart can no longer carry cover: take our line out.
		if (context.stainguard_item_code) {
			cartLine(context, context.stainguard_item_code).forEach((line: any) => context.remove_item(line));
			context.stainguard_item_code = null;
		}
		context.stainguard_status = emptyStainguardStatus();
		return;
	}

	const signature = context.stainguard_signature;
	context.stainguard_status = { ...context.stainguard_status, loading: true, message: "" };

	try {
		const total = context.flt(context.subtotal) - context.flt(context.delivery_charges_rate);
		const result = await api.call("customer_due_dates.staingard.pos.get_stainguard_offer", {
			total,
			lines: JSON.stringify(
				context.items.map((item: any) => ({
					item_code: item.item_code,
					amount: context.flt(item.qty) * context.flt(item.rate),
				})),
			),
		});

		if (signature !== context.stainguard_signature) {
			// The cart moved while we asked; the answer is for a cart that's gone.
			context._stainguardDirty = true;
			return;
		}

		const offer = result?.offer;
		const inCart = (context.items as any[]).filter((item) =>
			(result?.cart_item_codes || []).includes(item.item_code),
		);

		if (inCart.length === 1 && offer && inCart[0].item_code === offer.item_code) {
			context.stainguard_item_code = offer.item_code;
			context.stainguard_status = {
				loading: false,
				item_name: inCart[0].item_name || offer.item_name,
				rate: context.flt(inCart[0].rate),
				message: "",
			};
			return;
		}

		// Wrong band, a duplicate, or no cover wanted: clear ours out first.
		inCart.forEach((line) => context.remove_item(line));
		context.stainguard_item_code = null;

		if (!offer) {
			context.stainguard_status = {
				...emptyStainguardStatus(),
				message: __("No Stainguard cover for this order value"),
			};
			return;
		}

		// The same lookup and pricing the item list uses, so the cover is priced
		// like every other POS item (price list, customer pricing and all).
		const [item] =
			(await api.call("posawesome.posawesome.api.items.search_items_by_code", {
				pos_profile: context.pos_profile.name,
				price_list: context.get_price_list(),
				customer: context.customer,
				search_value: offer.item_code,
				exact: 1,
				limit: 1,
			})) || [];
		if (!item) {
			context.stainguard_status = {
				...emptyStainguardStatus(),
				message: __("Stainguard item {0} is not available in the POS", [offer.item_code]),
			};
			return;
		}

		// Tracked before the add so the cover never counts towards its own band.
		context.stainguard_item_code = offer.item_code;
		// NS items open their row for editing when added; the cover goes
		// straight into the cart instead.
		await context.add_item({ ...item, qty: 1, _skip_row_expansion: true });
		context.stainguard_status = {
			loading: false,
			item_name: item.item_name || offer.item_name,
			rate: context.flt(item.rate),
			message: "",
		};
	} catch (error) {
		console.error("Failed to sync Stainguard:", error);
		context.stainguard_status = emptyStainguardStatus();
	}
}
