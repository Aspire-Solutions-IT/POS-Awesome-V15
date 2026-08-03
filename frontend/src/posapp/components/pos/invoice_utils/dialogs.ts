import { isOffline } from "../../../../offline/index";
import { fetchDraftInvoices } from "../../../utils/draftInvoices";

declare const __: (_text: string, _args?: any[]) => string;
declare const frappe: any;

const showCompactPanel = (context: any, panel: "selector" | "invoice") => {
	context?.eventBus?.emit?.("set_compact_panel", panel);
};

const isCollectionChargeSelected = (context: any): boolean => {
	const selected = context?.selected_delivery_charge;
	if (selected && typeof selected === "object") {
		const flag = selected.collection;
		return flag === 1 || flag === "1" || flag === true;
	}

	const selectedName = String(
		context?.invoice_doc?.posa_delivery_charges || context?.selectedDeliveryCharge || "",
	).trim();
	if (!selectedName) {
		return false;
	}

	const rows = Array.isArray(context?.delivery_charges) ? context.delivery_charges : [];
	const row = rows.find((entry: any) => String(entry?.name || "").trim() === selectedName);
	const flag = row?.collection;
	return flag === 1 || flag === "1" || flag === true;
};

const hasOnlyNsItemsForCollection = (context: any): boolean => {
	if (!isCollectionChargeSelected(context)) {
		return true;
	}
	const lines = Array.isArray(context?.items) ? context.items : [];
	return lines.every((line: any) => String(line?.item_code || "").trim().toLowerCase().startsWith("ns"));
};

export async function show_payment(context: any) {
	if (context._suppressClosePaymentsTimer) {
		clearTimeout(context._suppressClosePaymentsTimer);
		context._suppressClosePaymentsTimer = null;
	}
	context._suppressClosePayments = true;

	// The posting date cache (context.invoiceStore.postingDate) is set once when the
	// store is created and only reset after a successful submission - if the POS page
	// is left open across midnight it keeps holding yesterday's date. When the cashier
	// has no way to edit it (posa_allow_change_posting_date is off), always re-derive
	// it from the real current date right before building the invoice/order, instead of
	// only refreshing on page load.
	if (!context.pos_profile?.posa_allow_change_posting_date && context.invoiceStore?.resetPostingDate) {
		context.invoiceStore.resetPostingDate();
		context.posting_date_display = context.formatDateForDisplay
			? context.formatDateForDisplay(context.invoiceStore.postingDate)
			: context.invoiceStore.postingDate;
	}

	try {
		if (!context.customer) {
			context.toastStore.show({
				title: __(`Select a customer`),
				color: "error",
			});
			return;
		}

		if (!context.items.length) {
			context.toastStore.show({
				title: __(`Select items to sell`),
				color: "error",
			});
			return;
		}

		if (!hasOnlyNsItemsForCollection(context)) {
			frappe.msgprint({
				title: __("Collection Not Allowed"),
				message: __("Only NS items can be collected."),
				indicator: "red",
			});
			return;
		}

		const isValid = context.validate ? await context.validate() : true;

		if (!isValid) {
			return;
		}

		if (context.ensure_auto_batch_selection) await context.ensure_auto_batch_selection();

		let invoice_doc;
		if (
			context.invoiceType === "Order" &&
			context.pos_profile.posa_create_only_sales_order &&
			!context.new_delivery_date &&
			!(context.invoice_doc && context.invoice_doc.posa_delivery_date)
		) {
			invoice_doc = context.get_invoice_doc();
		} else if (
			context.invoice_doc &&
			context.invoice_doc.doctype === "Sales Order" &&
			context.invoiceType === "Invoice"
		) {
			invoice_doc = await context.process_invoice_from_order();
		} else {
			invoice_doc = await context.process_invoice();
		}

		if (!invoice_doc) {
			return;
		}

		if (!isOffline() && invoice_doc.name) {
			const refreshed = await context.reload_current_invoice_from_backend();
			if (refreshed) {
				invoice_doc = refreshed;
			}
		}

		invoice_doc.currency = context.selected_currency || context.pos_profile.currency;
		invoice_doc.conversion_rate = context.conversion_rate || 1;
		invoice_doc.plc_conversion_rate = context._getPlcConversionRate ? context._getPlcConversionRate() : 1;

		if (invoice_doc.discount_amount !== undefined && invoice_doc.discount_amount !== null) {
			context.discount_amount = context.flt(invoice_doc.discount_amount, context.currency_precision);
			context.additional_discount = context.discount_amount;
		}

		if (
			invoice_doc.additional_discount_percentage !== undefined &&
			invoice_doc.additional_discount_percentage !== null
		) {
			context.additional_discount_percentage = context.flt(
				invoice_doc.additional_discount_percentage,
				context.float_precision,
			);
		}

		if (context.isReturnInvoice || invoice_doc.is_return) {
			// For return invoices, explicitly ensure all amounts are negative
			invoice_doc.is_return = 1;
			if (invoice_doc.grand_total > 0) invoice_doc.grand_total = -Math.abs(invoice_doc.grand_total);
			if (invoice_doc.rounded_total > 0)
				invoice_doc.rounded_total = -Math.abs(invoice_doc.rounded_total);
			if (invoice_doc.total > 0) invoice_doc.total = -Math.abs(invoice_doc.total);
			if (invoice_doc.base_grand_total > 0)
				invoice_doc.base_grand_total = -Math.abs(invoice_doc.base_grand_total);
			if (invoice_doc.base_rounded_total > 0)
				invoice_doc.base_rounded_total = -Math.abs(invoice_doc.base_rounded_total);
			if (invoice_doc.base_total > 0) invoice_doc.base_total = -Math.abs(invoice_doc.base_total);

			if (invoice_doc.items && invoice_doc.items.length) {
				invoice_doc.items.forEach((item) => {
					if (item.qty > 0) item.qty = -Math.abs(item.qty);
					if (item.stock_qty > 0) item.stock_qty = -Math.abs(item.stock_qty);
					if (item.amount > 0) item.amount = -Math.abs(item.amount);
				});
			}
		}

		invoice_doc.payments = context.get_payments ? context.get_payments() : [];

		if ((context.isReturnInvoice || invoice_doc.is_return) && invoice_doc.payments.length) {
			invoice_doc.payments.forEach((payment) => {
				if (payment.amount > 0) payment.amount = -Math.abs(payment.amount);
				if (payment.base_amount > 0) payment.base_amount = -Math.abs(payment.base_amount);
			});
		}

		await context.$nextTick();

		const useDesktopPaymentDialog =
			typeof window !== "undefined" && window.innerWidth >= 992;

		if (useDesktopPaymentDialog && context.uiStore?.openPaymentDialog) {
			context.uiStore.openPaymentDialog();
		} else if (context.uiStore?.setActiveView) {
			context.uiStore.closePaymentDialog?.();
			context.uiStore.setActiveView("payment");
		}
		showCompactPanel(context, "selector");

		if (typeof context.$nextTick === "function") {
			await context.$nextTick();
		}
		await new Promise((resolve) => setTimeout(resolve, 0));

		context.eventBus.emit("show_payment", "true");
		context.eventBus.emit("send_invoice_doc_payment", invoice_doc);
	} catch (error: any) {
		console.error("Error in show_payment:", error);
		context.toastStore.show({
			title: __("Error processing payment"),
			color: "error",
			message: error.message,
		});
	} finally {
		context._suppressClosePaymentsTimer = setTimeout(() => {
			context._suppressClosePayments = false;
			context._suppressClosePaymentsTimer = null;
		}, 300);
	}
}

export async function get_draft_invoices(context: any) {
	try {
		const drafts = await fetchDraftInvoices({
			posOpeningShift: context.pos_opening_shift,
			posProfile: context.pos_profile,
		});
		context.uiStore.setDraftsData?.(drafts);
		context.uiStore.setParkedOrders?.(drafts);
		context.uiStore.closeDrafts?.();

		if (drafts.length) {
			if (typeof context.$nextTick === "function") {
				await context.$nextTick();
			}
			context.$refs?.invoiceSummary?.openDraftsSurface?.();
		}
	} catch (error) {
		console.error("Error fetching draft invoices:", error);
		context.toastStore.show({
			title: __("Unable to fetch draft invoices"),
			color: "error",
		});
	}
}

export async function get_draft_orders(context: any) {
	try {
		const { message } = await frappe.call({
			method: "posawesome.posawesome.api.sales_orders.search_orders",
			args: {
				company: context.pos_profile.company,
				currency: context.pos_profile.currency,
			},
		});
		if (message) {
			context.uiStore.openOrders(message);
		}
	} catch (error) {
		console.error("Error fetching draft orders:", error);
		context.toastStore.show({
			title: __("Unable to fetch draft orders"),
			color: "error",
		});
	}
}


export function open_returns(context: any) {
	context.eventBus.emit("open_returns", context.pos_profile.company);
}

export function open_invoice_management(context: any, targetTab: string = "history") {
	context.uiStore?.openInvoiceManagement?.(targetTab);
}

export function close_payments(context: any) {
	if (context._suppressClosePayments) {
		return;
	}

	if (
		typeof context.paymentVisible !== "undefined" &&
		!context.paymentVisible &&
		!context.uiStore?.paymentDialogOpen
	) {
		return;
	}

	if (context.uiStore?.paymentDialogOpen && context.uiStore?.closePaymentDialog) {
		context.uiStore.closePaymentDialog();
	} else if (context.uiStore?.setActiveView) {
		context.uiStore.setActiveView("items");
	}
	showCompactPanel(context, "invoice");

	context.eventBus.emit("show_payment", "false");
}

export async function change_price_list_rate(
	context: any,
	item: any,
) {
	if (!item) return;

	const parseRate = (value: unknown) => {
		if (value === null || value === undefined) return null;
		const normalized = String(value).replace(/,/g, "").trim();
		if (!normalized) return null;
		const parsed = Number(normalized);
		if (!Number.isFinite(parsed)) return null;
		const rounded = context.flt
			? context.flt(parsed, context.currency_precision)
			: parsed;
		return rounded >= 0 ? rounded : null;
	};

	const applyRate = (nextRate: number) => {
		const priceCurrency =
			context.selected_currency ||
			context.price_list_currency ||
			context.pos_profile?.currency;
		if (context._applyPriceListRate) {
			context._applyPriceListRate(item, nextRate, priceCurrency);
		} else {
			item.price_list_rate = nextRate;
			item.base_price_list_rate = context._toBaseCurrency
				? context._toBaseCurrency(nextRate)
				: nextRate;
		}

		// Treat manual price-list change as an explicit rate override.
		item.rate = nextRate;
		item.base_rate = context._toBaseCurrency
			? context._toBaseCurrency(nextRate)
			: nextRate;
		item.discount_amount = 0;
		item.base_discount_amount = 0;
		item.discount_percentage = 0;
		item._manual_rate_set = true;
		item._manual_rate_set_from_uom = false;
		item.amount = context.flt
			? context.flt((item.qty || 0) * item.rate, context.currency_precision)
			: (item.qty || 0) * item.rate;
		item.base_amount = context._toBaseCurrency
			? context._toBaseCurrency(item.amount)
			: item.amount;

		if (typeof context.calc_stock_qty === "function") {
			context.calc_stock_qty(item, item.qty);
		}
		if (typeof context.schedulePricingRuleApplication === "function") {
			context.schedulePricingRuleApplication(true);
		}
		if (typeof context.forceUpdate === "function") {
			context.forceUpdate();
		}
	};

	const currentRate = parseRate(item.price_list_rate ?? item.rate ?? 0) ?? 0;
	let prompted: unknown = null;

	if (typeof context.promptPriceListRate === "function") {
		prompted = await context.promptPriceListRate(String(currentRate), item);
	} else if (
		typeof window !== "undefined" &&
		typeof window.prompt === "function"
	) {
		// Backward-compatible fallback when the host component has no custom dialog.
		prompted = window.prompt(__("Enter new price list rate"), String(currentRate));
	}

	if (prompted === null) {
		return;
	}
	const nextRate = parseRate(prompted);

	if (nextRate === null) {
		context.toastStore?.show?.({
			title: __("Invalid rate"),
			color: "error",
		});
		return;
	}

	applyRate(nextRate);
	item._price_list_rate_persisted = false;
}
