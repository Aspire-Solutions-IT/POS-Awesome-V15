import { describe, expect, it } from "vitest";

import { isValidOptionalEmail } from "../src/posapp/utils/emailValidation";

describe("isValidOptionalEmail", () => {
	it.each(["", "   ", null, undefined])("allows an empty optional value", (value) => {
		expect(isValidOptionalEmail(value)).toBe(true);
	});

	it.each(["customer@example.com", " First.Last+orders@example.co.uk "])(
		"accepts a single valid address",
		(value) => expect(isValidOptionalEmail(value)).toBe(true),
	);

	it.each(["customer", "customer@", "@example.com", "a@example.com,b@example.com", "a b@example.com"])(
		"rejects malformed or multiple addresses",
		(value) => expect(isValidOptionalEmail(value)).toBe(false),
	);
});
