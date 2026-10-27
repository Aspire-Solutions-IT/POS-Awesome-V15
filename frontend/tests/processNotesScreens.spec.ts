import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { ALL_POS_SCREENS, POS_SCREENS } from "../src/posapp/utils/processNotes";

const testsDir = path.dirname(fileURLToPath(import.meta.url));
const read = (...segments: string[]) => readFileSync(path.resolve(testsDir, ...segments), "utf8");

describe("process note POS screens", () => {
	// The POS matches notes to screens by router meta.title, and admins pick
	// screens from the Process Note Link select in customer_due_dates, so all
	// three lists have to agree.
	it("match a router title each, and the Process Note Link options", () => {
		const router = read("../src/posapp/router/index.ts");
		const titles = [...router.matchAll(/title:\s*"([^"]+)"/g)].map((m) => m[1]);
		for (const screen of POS_SCREENS) {
			expect(titles).toContain(screen);
		}

		const doctype = JSON.parse(
			read(
				"../../../customer_due_dates/customer_due_dates/process_notes/doctype/process_note_link/process_note_link.json",
			),
		);
		const options = doctype.fields
			.find((field: any) => field.fieldname === "pos_screen")
			.options.split("\n");
		expect(options).toEqual([ALL_POS_SCREENS, ...POS_SCREENS]);
	});
});
