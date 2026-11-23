// Ship-complete rules shared by the delivery charge list and the payment screen.
//
// A ship-complete charge (container order types) means the whole order goes out together, so
// it can never be split into delivery groups. Rows come from the server with a `ship_complete`
// flag; a row cached by an older build has none, so offline it cannot be trusted either way.

export type DeliveryChargeRow = {
	name?: string;
	ship_complete?: unknown;
	ship_complete_unverified?: boolean;
	[key: string]: unknown;
};

export const isTruthyFlag = (flag: unknown): boolean => flag === 1 || flag === "1" || flag === true;

export const isShipCompleteCharge = (row?: DeliveryChargeRow | null): boolean =>
	isTruthyFlag(row?.ship_complete);

/** A charge row without the flag: only a legacy cache row can look like this once the server is current. */
export const isLegacyChargeRow = (row?: DeliveryChargeRow | null): boolean =>
	Boolean(row) && (row as DeliveryChargeRow).ship_complete === undefined;

export const hasLegacyChargeRows = (rows: unknown): boolean =>
	Array.isArray(rows) && rows.some((row) => isLegacyChargeRow(row as DeliveryChargeRow));

/** Cached rows with no `ship_complete` are marked unverified: they must not offer a split. */
export const markUnverifiedCachedCharges = (rows: unknown): DeliveryChargeRow[] =>
	(Array.isArray(rows) ? rows : []).map((row: DeliveryChargeRow) =>
		isLegacyChargeRow(row) ? { ...row, ship_complete_unverified: true } : row,
	);

/** Whether the split-delivery option (and the grouping step) may be offered for this charge. */
export const canSplitDelivery = (
	row: DeliveryChargeRow | null | undefined,
	isCollectionCharge: boolean,
): boolean => !isCollectionCharge && !isShipCompleteCharge(row) && !row?.ship_complete_unverified;
