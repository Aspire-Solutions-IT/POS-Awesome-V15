/** Empty email fields are allowed, but populated fields must contain one address. */
export function isValidOptionalEmail(value: unknown): boolean {
	const email = String(value ?? "").trim();
	return !email || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}
