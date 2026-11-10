import { parseBooleanSetting } from "./stock";

export const stainguardSyncMutation = Symbol("stainguard-checkbox-sync");

export function isStainguardItem(
	item: any,
	trackedCode?: string | null,
): boolean {
	return Boolean(
		item &&
			(parseBooleanSetting(item.is_staingard_item) ||
				(trackedCode && item.item_code === trackedCode)),
	);
}
