export const MAX_PIN_LENGTH = 8;

export const sanitizePinInput = (
	value: unknown,
	maxLength: number = MAX_PIN_LENGTH,
) =>
	String(value ?? "")
		.replace(/\D/g, "")
		.slice(0, maxLength);
