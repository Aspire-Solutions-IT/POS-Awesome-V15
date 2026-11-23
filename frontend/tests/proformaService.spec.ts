import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
	describeProformaResult,
	normaliseProformaResponse,
	sendProforma,
} from "../src/posapp/services/proformaService";

const tr = (value: string, args?: any[]) =>
	args?.length ? value.replace(/\{(\d+)\}/g, (_m, i) => String(args[Number(i)] ?? "")) : value;

describe("normaliseProformaResponse", () => {
	it("reads the documented fields", () => {
		expect(
			normaliseProformaResponse({
				message: { ok: true, link: "https://pay/x", email_sent: true, attachment_ok: true, error: "" },
			}),
		).toEqual({ ok: true, link: "https://pay/x", emailSent: true, attachmentOk: true, error: "" });
	});

	it("tolerates missing fields and a missing body", () => {
		expect(normaliseProformaResponse({ message: { ok: true } })).toMatchObject({
			ok: true,
			emailSent: false,
			attachmentOk: true,
			link: "",
		});
		expect(normaliseProformaResponse(undefined).ok).toBe(false);
		expect(normaliseProformaResponse({}).ok).toBe(false);
	});

	it("strips markup from a server error", () => {
		expect(normaliseProformaResponse({ message: { ok: false, error: "<b>No</b> email" } }).error).toBe(
			"No email",
		);
	});
});

describe("describeProformaResult", () => {
	const base = { ok: true, link: "l", emailSent: true, attachmentOk: true, error: "" };

	it("success names the recipient when known", () => {
		const out = describeProformaResult(base, tr, "a@b.c");
		expect(out).toMatchObject({ state: "sent", level: "success", canRetry: false });
		expect(out.message).toContain("a@b.c");
	});

	it("warns when the email went without its PDF", () => {
		const out = describeProformaResult({ ...base, attachmentOk: false }, tr);
		expect(out).toMatchObject({ state: "attachment_missing", level: "warning", canRetry: true });
	});

	it("link only: email not sent, with the reason", () => {
		const out = describeProformaResult({ ...base, emailSent: false, error: "No email address" }, tr);
		expect(out).toMatchObject({ state: "link_only", level: "warning", canRetry: true });
		expect(out.message).toContain("No email address");
	});

	it("failure keeps the order-saved wording and offers retry", () => {
		const out = describeProformaResult({ ...base, ok: false, link: "", emailSent: false }, tr);
		expect(out).toMatchObject({ state: "failed", level: "error", canRetry: true });
		expect(out.message).toContain("order was saved");
		expect(describeProformaResult({ ...base, ok: false, error: "Boom" }, tr).message).toBe("Boom");
	});
});

describe("sendProforma", () => {
	beforeEach(() => vi.unstubAllGlobals());
	afterEach(() => vi.unstubAllGlobals());

	it("posts the order and only sends resend when asked", async () => {
		const call = vi.fn((opts: any) =>
			opts.callback({ message: { ok: true, link: "l", email_sent: true, attachment_ok: true } }),
		);
		vi.stubGlobal("frappe", { call });

		const result = await sendProforma("SO-1");
		expect(call.mock.calls[0][0]).toMatchObject({
			method: "posawesome.posawesome.api.sales_orders.send_proforma",
			type: "POST",
			args: { sales_order: "SO-1" },
		});
		expect(call.mock.calls[0][0].args.resend).toBeUndefined();
		expect(result.emailSent).toBe(true);

		await sendProforma("SO-1", { resend: true });
		expect(call.mock.calls[1][0].args.resend).toBe(1);
	});

	it("never throws: a failed request comes back as ok false", async () => {
		vi.stubGlobal("frappe", { call: (opts: any) => opts.error({ message: "Network down" }) });
		await expect(sendProforma("SO-1")).resolves.toMatchObject({ ok: false, error: "Network down" });
	});
});
