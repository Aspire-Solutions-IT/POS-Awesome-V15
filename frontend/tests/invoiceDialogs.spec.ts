// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";

import { close_payments, show_payment } from "../src/posapp/components/pos/invoice_utils/dialogs";

const createPaymentContext = () => ({
	_suppressClosePaymentsTimer: null,
	_suppressClosePayments: false,
	customer: "CUST-001",
	items: [{ item_code: "ITEM-001" }],
	validate: vi.fn(async () => true),
	ensure_auto_batch_selection: vi.fn(async () => {}),
	invoiceType: "Invoice",
	pos_profile: { currency: "USD" },
	invoice_doc: {},
	currentCashier: { user: "cashier@example.com" },
	yellowTicketPhotoGate: {
		ensureYellowTicketPhotos: vi.fn(async (..._args: unknown[]) => undefined as unknown),
	},
	process_invoice: vi.fn(async () => ({
		doctype: "Sales Invoice",
		grand_total: 10,
		rounded_total: 10,
		total: 10,
		payments: [],
	})),
	process_invoice_from_order: vi.fn(),
	reload_current_invoice_from_backend: vi.fn(),
	selected_currency: "USD",
	conversion_rate: 1,
	_getPlcConversionRate: () => 1,
	flt: (value: unknown) => Number(value || 0),
	currency_precision: 2,
	float_precision: 2,
	isReturnInvoice: false,
	get_payments: () => [],
	$nextTick: async () => {},
	uiStore: {
		openPaymentDialog: vi.fn(),
		closePaymentDialog: vi.fn(),
		setActiveView: vi.fn(),
	},
	eventBus: { emit: vi.fn() },
	toastStore: { show: vi.fn() },
});

describe("invoice payment dialogs", () => {
	beforeEach(() => {
		vi.stubGlobal("__", (value: string) => value);
		vi.stubGlobal("frappe", { call: vi.fn() });
		Object.defineProperty(window, "innerWidth", {
			value: 500,
			writable: true,
			configurable: true,
		});
	});

	it("switches compact layout to the selector when opening payments", async () => {
		const context = createPaymentContext();

		await show_payment(context);

		expect(context.uiStore.setActiveView).toHaveBeenCalledWith("payment");
		expect(context.eventBus.emit).toHaveBeenCalledWith("set_compact_panel", "selector");
		expect(context.eventBus.emit).toHaveBeenCalledWith("show_payment", "true");
	});

	it("keeps the Stainguard checkbox state after refreshing the payment document", async () => {
		const context = { ...createPaymentContext(), stainguard_enabled: true };
		context.process_invoice.mockResolvedValueOnce({ name: "ORDER-1" } as any);
		context.reload_current_invoice_from_backend.mockResolvedValueOnce({ name: "ORDER-1", items: [] } as any);
		await show_payment(context);
		expect(context.eventBus.emit).toHaveBeenCalledWith(
			"send_invoice_doc_payment",
			expect.objectContaining({ posa_stainguard_enabled: true }),
		);
	});

	it.each([500, 1200])("waits for photos before opening payment at width %s", async (width) => {
		window.innerWidth = width;
		const context = createPaymentContext();
		let finishPhotos!: (result: unknown) => void;
		context.yellowTicketPhotoGate.ensureYellowTicketPhotos.mockImplementationOnce(
			() => new Promise((resolve) => { finishPhotos = resolve; }),
		);
		const checkout = show_payment(context);
		await vi.waitFor(() => expect(finishPhotos).toBeTypeOf("function"));
		expect(context.process_invoice).toHaveBeenCalledOnce();
		expect(context.yellowTicketPhotoGate.ensureYellowTicketPhotos).toHaveBeenCalledWith(
			context.pos_profile,
			expect.objectContaining({ doctype: "Sales Invoice" }),
			"Invoice",
			"cashier@example.com",
		);
		expect(context.uiStore.openPaymentDialog).not.toHaveBeenCalled();
		expect(context.uiStore.setActiveView).not.toHaveBeenCalled();
		expect(context.eventBus.emit).not.toHaveBeenCalled();
		await show_payment(context);
		expect(context.yellowTicketPhotoGate.ensureYellowTicketPhotos).toHaveBeenCalledOnce();
		finishPhotos({ photos_owed: 0 });
		await checkout;
		if (width >= 992) {
			expect(context.uiStore.openPaymentDialog).toHaveBeenCalledOnce();
		} else {
			expect(context.uiStore.setActiveView).toHaveBeenCalledWith("payment");
		}
		expect(context.eventBus.emit).toHaveBeenCalledWith("show_payment", "true");
	});

	it("stays on the sale when photos are cancelled and allows retrying", async () => {
		const context = createPaymentContext();
		context.yellowTicketPhotoGate.ensureYellowTicketPhotos.mockResolvedValueOnce(false);
		await show_payment(context);
		expect(context.uiStore.openPaymentDialog).not.toHaveBeenCalled();
		expect(context.uiStore.setActiveView).not.toHaveBeenCalled();
		expect(context.eventBus.emit).not.toHaveBeenCalled();
		await show_payment(context);
		expect(context.uiStore.setActiveView).toHaveBeenCalledWith("payment");
	});

	it("checks photos against the refreshed document before payment", async () => {
		const context = createPaymentContext();
		context.process_invoice.mockResolvedValueOnce({ name: "ORDER-1" } as any);
		const refreshed = { name: "ORDER-1", items: [{ item_code: "NS-SOFA", posa_row_id: "row-1" }] };
		context.reload_current_invoice_from_backend.mockResolvedValueOnce(refreshed);
		await show_payment(context);
		expect(context.yellowTicketPhotoGate.ensureYellowTicketPhotos.mock.calls[0][1]).toBe(refreshed);
	});

	it("does not prompt for photos when sale validation fails", async () => {
		const context = createPaymentContext();
		context.validate.mockResolvedValueOnce(false);
		await show_payment(context);
		expect(context.yellowTicketPhotoGate.ensureYellowTicketPhotos).not.toHaveBeenCalled();
		expect(context.uiStore.setActiveView).not.toHaveBeenCalled();
	});

	it("does not block payment if the photo check itself fails", async () => {
		const context = createPaymentContext();
		const errorLog = vi.spyOn(console, "error").mockImplementation(() => {});
		context.yellowTicketPhotoGate.ensureYellowTicketPhotos.mockRejectedValueOnce(new Error("Unavailable"));
		try {
			await show_payment(context);
			expect(context.uiStore.setActiveView).toHaveBeenCalledWith("payment");
		} finally {
			errorLog.mockRestore();
		}
	});

	it("switches compact layout back to the invoice when closing payments", () => {
		const context = {
			_suppressClosePayments: false,
			paymentVisible: true,
			uiStore: {
				paymentDialogOpen: false,
				closePaymentDialog: vi.fn(),
				setActiveView: vi.fn(),
			},
			eventBus: { emit: vi.fn() },
		};

		close_payments(context);

		expect(context.uiStore.setActiveView).toHaveBeenCalledWith("items");
		expect(context.eventBus.emit).toHaveBeenCalledWith("set_compact_panel", "invoice");
		expect(context.eventBus.emit).toHaveBeenCalledWith("show_payment", "false");
	});
});
