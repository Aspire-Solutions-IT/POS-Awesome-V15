// Ship-complete rules shared by the delivery charge list and the payment screen.
//
// A ship-complete charge (container order types) means the whole order goes out together, so
// it can never be split into delivery groups. Rows come from the server with a `ship_complete`
// flag; a row cached by an older build has none, so offline it cannot be trusted either way.

export type DeliveryChargeRow = {
	name?: string;
	ship_complete?: unknown;
	ship_complete_unverified?: boolean;
	order_type_unverified?: boolean;
	[key: string]: unknown;
};

export const isTruthyFlag = (flag: unknown): boolean => flag === 1 || flag === "1" || flag === true;

export const isShipCompleteCharge = (row?: DeliveryChargeRow | null): boolean =>
	isTruthyFlag(row?.ship_complete);

/** A charge row without the flag: only a legacy cache row can look like this once the server is current. */
export const isLegacyChargeRow = (row?: DeliveryChargeRow | null): boolean =>
	Boolean(row) && (row as DeliveryChargeRow).ship_complete === undefined;

/** A charge row with no `order_type_name` key cannot say whether it is a DHD charge (legacy cache). */
export const lacksOrderTypeName = (row?: DeliveryChargeRow | null): boolean =>
	Boolean(row) && (row as DeliveryChargeRow).order_type_name === undefined;

export const hasLegacyChargeRows = (rows: unknown): boolean =>
	Array.isArray(rows) &&
	rows.some(
		(row) => isLegacyChargeRow(row as DeliveryChargeRow) || lacksOrderTypeName(row as DeliveryChargeRow),
	);

/**
 * Cached rows with no `ship_complete` are marked unverified: they must not offer a split.
 * Cached rows with no `order_type_name` are marked too: they cannot be told apart from a DHD
 * charge, so submitting an order on one is blocked until the charge is reloaded.
 */
export const markUnverifiedCachedCharges = (rows: unknown): DeliveryChargeRow[] =>
	(Array.isArray(rows) ? rows : []).map((row: DeliveryChargeRow) => {
		let marked = row;
		if (isLegacyChargeRow(row)) {
			marked = { ...marked, ship_complete_unverified: true };
		}
		if (lacksOrderTypeName(row)) {
			marked = { ...marked, order_type_unverified: true };
		}
		return marked;
	});

/** True when the selected charge's DHD status could not be verified (see markUnverifiedCachedCharges). */
export const isOrderTypeUnverified = (row?: DeliveryChargeRow | null): boolean =>
	Boolean(row?.order_type_unverified);

/** Whether the split-delivery option (and the grouping step) may be offered for this charge. */
export const canSplitDelivery = (
	row: DeliveryChargeRow | null | undefined,
	isCollectionCharge: boolean,
): boolean => !isCollectionCharge && !isShipCompleteCharge(row) && !row?.ship_complete_unverified;
