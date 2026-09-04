export const ACTIVE_OPENING_SHIFT_KEY = "posa_active_opening_shift";

const getBrowserGlobal = (): any =>
	typeof window !== "undefined" ? window : globalThis;

/**
 * The opening shift this terminal was last operating.
 *
 * A user may hold one open shift per POS Profile (see `switch_pos_profile`), so the
 * newest open shift on the server is not necessarily the active one. This key is what
 * pins the terminal to the profile the cashier actually chose.
 */
export function getActiveOpeningShiftName(): string {
	try {
		return getBrowserGlobal()?.localStorage?.getItem(ACTIVE_OPENING_SHIFT_KEY) || "";
	} catch {
		return "";
	}
}

export function setActiveOpeningShiftName(shiftName?: string | null) {
	try {
		const storage = getBrowserGlobal()?.localStorage;
		if (!storage) {
			return;
		}
		if (shiftName) {
			storage.setItem(ACTIVE_OPENING_SHIFT_KEY, String(shiftName));
		} else {
			storage.removeItem(ACTIVE_OPENING_SHIFT_KEY);
		}
	} catch {
		// Ignore storage failures.
	}
}

export function clearActiveOpeningShiftName() {
	setActiveOpeningShiftName(null);
}

export function hasCachedOpeningData(openingData: any): boolean {
	return !!(
		openingData &&
		openingData.pos_profile &&
		openingData.pos_opening_shift &&
		openingData.pos_opening_shift.user
	);
}

export function isCachedOpeningValidForCurrentUser(
	openingData: any,
	currentUser?: string | null,
): boolean {
	if (!hasCachedOpeningData(openingData)) {
		return false;
	}
	const cachedUser = openingData?.pos_opening_shift?.user;
	if (!currentUser || !cachedUser) {
		return false;
	}
	if (currentUser !== cachedUser) {
		return false;
	}

	// With one open shift per profile, a cache entry for a profile the cashier has
	// since switched away from is stale even though it belongs to the right user.
	const activeShift = getActiveOpeningShiftName();
	if (activeShift && openingData?.pos_opening_shift?.name !== activeShift) {
		return false;
	}

	return true;
}

export function getValidCachedOpeningForCurrentUser(
	openingData: any,
	currentUser?: string | null,
) {
	if (!isCachedOpeningValidForCurrentUser(openingData, currentUser)) {
		return null;
	}
	return openingData;
}

export function getCachedOpeningBootstrapSeed(openingData: any) {
	if (!hasCachedOpeningData(openingData)) {
		return null;
	}

	return {
		profileName: openingData?.pos_profile?.name || null,
		profileModified: openingData?.pos_profile?.modified || null,
		openingShiftName: openingData?.pos_opening_shift?.name || null,
		openingShiftUser: openingData?.pos_opening_shift?.user || null,
	};
}
