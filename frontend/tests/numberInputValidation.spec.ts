import { describe, expect, it } from "vitest";

import { isNumberInput } from "../src/posapp/format";

describe("isNumberInput", () => {
	it("accepts decimals typed with a dot", () => {
		expect(isNumberInput("12.5")).toBe(true);
		expect(isNumberInput("0.75")).toBe(true);
		expect(isNumberInput("12.50")).toBe(true);
		expect(isNumberInput("-2.5")).toBe(true);
	});

	it("accepts a decimal that is still being typed", () => {
		expect(isNumberInput("12.")).toBe(true);
		expect(isNumberInput(".5")).toBe(true);
	});

	it("accepts an empty box", () => {
		expect(isNumberInput("")).toBe(true);
		expect(isNumberInput(null)).toBe(true);
		expect(isNumberInput(undefined)).toBe(true);
	});

	it("accepts plain integers and thousands separators", () => {
		expect(isNumberInput("1234")).toBe(true);
		expect(isNumberInput("1,234")).toBe(true);
		expect(isNumberInput("1,234,567.89")).toBe(true);
	});

	it("accepts Arabic-Indic digits and separators", () => {
		expect(isNumberInput("١٢٫٥")).toBe(true);
		expect(isNumberInput("١٬٢٣٤٫٥٦")).toBe(true);
	});

	it("rejects values that are not numbers", () => {
		expect(isNumberInput("abc")).toBe("invalid number");
		expect(isNumberInput("12.3.4")).toBe("invalid number");
		expect(isNumberInput("1,23")).toBe("invalid number");
		expect(isNumberInput(".")).toBe("invalid number");
		expect(isNumberInput("-")).toBe("invalid number");
	});
});
