/**
 * Supply-based split suggestions from the cart's delivery estimate.
 *
 * "Estimate Delivery" records each cart row's supply type on the row as
 * `posa_supply_type`. The split-order step can then offer one group per supply
 * type, so stock that can go now isn't held back by lines waiting on a
 * container or a lead time.
 */

declare const __: (_text: string, _args?: any[]) => string;

export const SUPPLY_TYPE_FIELD = "posa_supply_type";

// Earliest supply first; this is also the order the suggested groups appear in.
const SUPPLY_ORDER = ["Allocated", "Pre Allocated", "Lead Time"];

const supplyRank = (supply: string) => {
	const index = SUPPLY_ORDER.indexOf(supply);
	return index === -1 ? SUPPLY_ORDER.length : index;
};

const rowId = (item: any) => String(item?.posa_row_id || "").trim();

/**
 * Identity of the cart for estimate purposes: rows, items, quantities and UOMs.
 * Any change to it means the stored supply types no longer describe the cart.
 */
export function cartSupplySignature(items: any[]): string {
	return (Array.isArray(items) ? items : [])
		.map((item) => [rowId(item), item?.item_code, Number(item?.qty) || 0, item?.uom || ""].join("|"))
		.join(";");
}

/**
 * Supply type per cart row from the estimate lines. A cart row that expanded
 * into several order lines (kits) takes its slowest supply.
 */
export function supplyByRowId(lines: any[]): Record<string, string> {
	const result: Record<string, string> = {};
	(Array.isArray(lines) ? lines : []).forEach((line) => {
		const id = rowId(line);
		const supply = String(line?.source || "").trim();
		if (!id || !supply) {
			return;
		}
		if (!result[id] || supplyRank(supply) > supplyRank(result[id])) {
			result[id] = supply;
		}
	});
	return result;
}

export function applySupplyTypes(items: any[], supplies: Record<string, string>) {
	(Array.isArray(items) ? items : []).forEach((item) => {
		const supply = supplies[rowId(item)];
		if (supply) {
			item[SUPPLY_TYPE_FIELD] = supply;
		} else {
			delete item[SUPPLY_TYPE_FIELD];
		}
	});
}

export function clearSupplyTypes(items: any[]) {
	(Array.isArray(items) ? items : []).forEach((item) => {
		if (item && SUPPLY_TYPE_FIELD in item) {
			delete item[SUPPLY_TYPE_FIELD];
		}
	});
}

/** Supply type recorded on the cart rows, keyed by row id. */
export function storedSupplyByRowId(items: any[]): Record<string, string> {
	const result: Record<string, string> = {};
	(Array.isArray(items) ? items : []).forEach((item) => {
		const id = rowId(item);
		if (id && item?.[SUPPLY_TYPE_FIELD]) {
			result[id] = item[SUPPLY_TYPE_FIELD];
		}
	});
	return result;
}

/** True only when every row with a row id carries a supply type. */
export function hasCompleteSupplyTypes(items: any[]): boolean {
	const rows = (Array.isArray(items) ? items : []).filter((item) => rowId(item));
	return rows.length > 0 && rows.every((item) => Boolean(item?.[SUPPLY_TYPE_FIELD]));
}

/**
 * One split group per supply type, earliest supply first. The first group
 * reuses `defaultGroupId` so it stays the group that can't be removed.
 */
export function buildSuggestedSplitGroups(
	orderItems: any[],
	supplies: Record<string, string>,
	defaultGroupId: string,
) {
	const buckets = new Map<string, string[]>();
	(Array.isArray(orderItems) ? orderItems : []).forEach((item) => {
		const id = rowId(item);
		if (!id) {
			return;
		}
		const supply = supplies[id] || "Lead Time";
		if (!buckets.has(supply)) {
			buckets.set(supply, []);
		}
		buckets.get(supply)!.push(id);
	});

	return Array.from(buckets.keys())
		.sort((a, b) => supplyRank(a) - supplyRank(b) || a.localeCompare(b))
		.map((supply, index) => ({
			group_id: index === 0 ? defaultGroupId : `supply-${supply.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
			label: __(supply),
			row_ids: buckets.get(supply)!,
		}));
}
