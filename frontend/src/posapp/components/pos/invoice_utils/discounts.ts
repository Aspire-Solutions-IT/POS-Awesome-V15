import { useDiscounts } from "../../../composables/pos/shared/useDiscounts";

let discountsApi: ReturnType<typeof useDiscounts> | null = null;

function getDiscountsApi() {
	if (!discountsApi) {
		discountsApi = useDiscounts();
	}
	return discountsApi;
}

export function update_discount_umount(context: any) {
	const { updateDiscountAmount } = getDiscountsApi();
	return updateDiscountAmount(context);
}

/** Live percentage -> amount sync, used while the operator types in the % box. */
export function sync_discount_amount_from_percentage(context: any) {
	const { syncDiscountAmountFromPercentage } = getDiscountsApi();
	return syncDiscountAmountFromPercentage(context);
}

/** Live amount -> percentage sync, used while the operator types in the amount box. */
export function sync_discount_percentage_from_amount(
	context: any,
	options: { force?: boolean } = {},
) {
	const { syncDiscountPercentageFromAmount } = getDiscountsApi();
	return syncDiscountPercentageFromAmount(context, options);
}

/** Commits an amount entry: mirrors it to % and enforces the POS Profile ceiling. */
export function commit_discount_amount(context: any) {
	const { commitDiscountAmount } = getDiscountsApi();
	return commitDiscountAmount(context);
}

export function calc_prices(context: any, item: any, value: any, $event: any) {
	const { calcPrices } = getDiscountsApi();
	const outcome = calcPrices(item, value, $event, context);
	if (context.schedulePricingRuleApplication) {
		context.schedulePricingRuleApplication();
	}
	return outcome;
}

export function calc_item_price(context: any, item: any) {
	const { calcItemPrice } = getDiscountsApi();
	const outcome = calcItemPrice(item, context);
	if (context.schedulePricingRuleApplication) {
		context.schedulePricingRuleApplication();
	}
	return outcome;
}
