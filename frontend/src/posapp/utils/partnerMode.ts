/**
 * Locked-down Sales Partner POS (AP-1).
 *
 * The server tells the browser it is in partner mode through `frappe.boot.posa_partner_mode`,
 * which carries the same allow-list the server enforces (`partner_gate.py`). Mirroring that
 * one list means the UI never fires a call the server would refuse, so a partner never sees
 * "not permitted" dialogs from features that are simply switched off for them, and the two
 * can't drift apart. The server is still the only thing that protects data.
 */

declare const frappe: any;

export type PartnerModeConfig = {
	partners: string[];
	allowed_methods: string[];
	customer_methods: string[];
	shorthand_allowed: string[];
	framework_denied: string[];
	framework_allowed: string[];
};

/** Routes a partner may open; everything else bounces back to the POS. */
export const PARTNER_HOME_ROUTE = "/pos";
export const PARTNER_ALLOWED_ROUTES = ["/pos", "/sales-orders"];

const GUARD_MARKER = "__posaPartnerCallGuard";

type CustomerProvider = () => string | null | undefined;
let customerProvider: CustomerProvider = () => null;

/** Where the guard reads the customer the partner has selected. Set once at startup. */
export function setPartnerCustomerProvider(provider: CustomerProvider) {
	customerProvider = provider;
}

/**
 * Item prices, and customer data, are per customer for a partner. The POS fetches items from
 * many places, not all of which pass the customer, so the guard supplies the selected one.
 * Returns the args to send, or `null` when the call can't be made yet (no customer chosen).
 */
export function resolvePartnerCallArgs(
	method: string,
	args: any,
	config: PartnerModeConfig | null = getPartnerMode(),
): any | null {
	const name = (String(method || "").split("/")[0] ?? "").trim();
	if (!config || !config.customer_methods.includes(name)) {
		return args;
	}
	if (args && typeof args === "object" && args.customer) {
		return args;
	}
	const customer = customerProvider();
	if (!customer) {
		return null;
	}
	return { ...(args && typeof args === "object" ? args : {}), customer };
}

const getBrowserGlobal = (): any =>
	typeof window !== "undefined" ? window : globalThis;

export function getPartnerMode(): PartnerModeConfig | null {
	const config = getBrowserGlobal()?.frappe?.boot?.posa_partner_mode;
	if (!config || typeof config !== "object") {
		return null;
	}
	return {
		partners: config.partners || [],
		allowed_methods: config.allowed_methods || [],
		customer_methods: config.customer_methods || [],
		shorthand_allowed: config.shorthand_allowed || [],
		framework_denied: config.framework_denied || [],
		framework_allowed: config.framework_allowed || [],
	};
}

export function isPartnerMode(): boolean {
	return getPartnerMode() !== null;
}

/** Mirrors `partner_gate._rule_for`, minus the per-argument scope checks. */
export function isMethodAllowedForPartner(
	method: string,
	config: PartnerModeConfig | null = getPartnerMode(),
): boolean {
	if (!config) {
		return true;
	}

	// Frappe runs only the part before the first "/".
	const name = (String(method || "").split("/")[0] ?? "").trim();
	if (!name) {
		return false;
	}
	if (config.allowed_methods.includes(name) || config.shorthand_allowed.includes(name)) {
		return true;
	}
	if (!name.startsWith("frappe.")) {
		return false;
	}
	if (config.framework_allowed.includes(name)) {
		return true;
	}
	return !config.framework_denied.some((entry) =>
		entry.endsWith(".") ? name.startsWith(entry) : name === entry,
	);
}

export function isRouteAllowedForPartner(path: string): boolean {
	const clean = String(path || "").split(/[?#]/)[0] ?? "";
	return PARTNER_ALLOWED_ROUTES.some(
		(allowed) => clean === allowed || clean.startsWith(`${allowed}/`),
	);
}

/**
 * Makes `frappe.call` / `frappe.xcall` resolve quietly, without touching the network, for
 * any method the server would refuse a partner. The ~150 call sites in the POS don't each
 * need to know about partners: the disabled features just get an empty answer.
 */
export function installPartnerCallGuard(target: any = getBrowserGlobal()?.frappe) {
	if (!target || !isPartnerMode() || target[GUARD_MARKER]) {
		return;
	}

	const originalCall = target.call;
	if (typeof originalCall === "function") {
		const guardedCall = function (this: any, first: any, ...rest: any[]) {
			const method = typeof first === "string" ? first : first?.method;
			if (method && !isMethodAllowedForPartner(method)) {
				console.debug("Partner mode: skipped call", method);
				return Promise.resolve({ message: undefined });
			}
			if (method) {
				if (typeof first === "string") {
					const args = resolvePartnerCallArgs(method, rest[0]);
					if (args === null) {
						console.debug("Partner mode: no customer yet, skipped", method);
						return Promise.resolve({ message: undefined });
					}
					return originalCall.call(target, first, args, ...rest.slice(1));
				}
				const args = resolvePartnerCallArgs(method, first.args);
				if (args === null) {
					console.debug("Partner mode: no customer yet, skipped", method);
					return Promise.resolve({ message: undefined });
				}
				if (args !== first.args) {
					return originalCall.call(target, { ...first, args }, ...rest);
				}
			}
			return originalCall.call(target, first, ...rest);
		};
		target.call = Object.assign(guardedCall, originalCall);
	}

	const originalXcall = target.xcall;
	if (typeof originalXcall === "function") {
		const guardedXcall = function (this: any, method: string, ...rest: any[]) {
			if (method && !isMethodAllowedForPartner(method)) {
				console.debug("Partner mode: skipped call", method);
				return Promise.resolve(undefined);
			}
			if (method) {
				const args = resolvePartnerCallArgs(method, rest[0]);
				if (args === null) {
					console.debug("Partner mode: no customer yet, skipped", method);
					return Promise.resolve(undefined);
				}
				return originalXcall.call(target, method, args, ...rest.slice(1));
			}
			return originalXcall.call(target, method, ...rest);
		};
		target.xcall = Object.assign(guardedXcall, originalXcall);
	}

	target[GUARD_MARKER] = true;
}
