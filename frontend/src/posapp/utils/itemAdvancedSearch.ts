/**
 * Item "Advanced Search" dialog, identical to the one on desk Item link fields.
 *
 * Reuses Frappe's own LinkSelector with an adapter target in place of a link
 * control, so the dialog, paging and result columns match desk exactly.
 */

declare const frappe: any;

// Wraps erpnext.controllers.queries.item_query and drops items excluded from POS.
export const ITEM_ADVANCED_SEARCH_QUERY =
	"posawesome.posawesome.api.item_processing.search.item_advanced_search_query";

export interface OpenItemAdvancedSearchParams {
	txt?: string;
	context?: string;
	customer?: string | null;
	onSelect: (_itemCode: string) => void;
}

/**
 * Mirrors the Item link query ERPNext sets on transaction item tables.
 */
export const buildItemAdvancedSearchFilters = (
	context: string | undefined,
	customer: string | null | undefined,
): Record<string, any> => {
	if (context === "purchase") {
		return { is_purchase_item: 1, has_variants: 0 };
	}
	const filters: Record<string, any> = { is_sales_item: 1, has_variants: 0 };
	if (customer) {
		filters.customer = customer;
	}
	return filters;
};

export const openItemAdvancedSearch = ({
	txt = "",
	context,
	customer,
	onSelect,
}: OpenItemAdvancedSearchParams): any => {
	const target = {
		set_custom_query(args: Record<string, any>) {
			args.query = ITEM_ADVANCED_SEARCH_QUERY;
			args.filters = buildItemAdvancedSearchFilters(context, customer);
		},
		set_input(value: string) {
			if (value) {
				onSelect(value);
			}
		},
		$input: { trigger() {} },
	};

	return new frappe.ui.form.LinkSelector({
		doctype: "Item",
		txt: String(txt || ""),
		target,
	});
};
