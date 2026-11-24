import { ref } from "vue";

/**
 * The delivery charge on the current order, as far as pricing is concerned (AP-1).
 *
 * A container charge (FOB, DDP) fixes the price list for the whole order, so item prices
 * come from `chargeLockedPriceList` instead of the customer's list. Every item request
 * also carries the charge name, so the server can apply the same lock and the per-item
 * fallback (customer list, then Stockist or DHD) that it enforces when the order is saved.
 */
export const selectedChargeName = ref("");
export const chargeLockedPriceList = ref<string | null>(null);

export const setChargePricing = (charge: Record<string, any> | null | undefined) => {
	selectedChargeName.value = charge?.name || "";
	chargeLockedPriceList.value =
		charge?.price_list && Number(charge?.price_list_overrides_customer)
			? String(charge.price_list)
			: null;
};

/** Extra request arguments naming the order's delivery charge (empty when there is none). */
export const chargeRequestArgs = (): { delivery_charge?: string } =>
	selectedChargeName.value ? { delivery_charge: selectedChargeName.value } : {};
