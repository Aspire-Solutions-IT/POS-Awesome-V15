/**
 * Which Sales Order submit buttons the payment step offers (AP-12).
 *
 * Staff keep "Submit Without Payment" where the POS Profile is order-only, plus On Account
 * when it is switched on. A Sales Partner places orders, and when On Account and/or Pro
 * Forma is available those replace "Place Order"; only a partner whose profile offers
 * neither keeps Place Order, so they are never left without a way to submit.
 */
export type PaymentTypeOptionInputs = {
	isPartner: boolean;
	/** The invoice being paid is a Sales Order ("Order"), not an invoice. */
	isOrder: boolean;
	/** The POS Profile only creates Sales Orders (posa_create_only_sales_order). */
	createOnlySalesOrder: boolean;
	allowOnAccount: boolean;
	allowProforma: boolean;
};

export type PaymentTypeOptions = {
	showSubmitWithoutPayment: boolean;
	showOnAccount: boolean;
	showProforma: boolean;
};

export function resolvePaymentTypeOptions({
	isPartner,
	isOrder,
	createOnlySalesOrder,
	allowOnAccount,
	allowProforma,
}: PaymentTypeOptionInputs): PaymentTypeOptions {
	const orderTypesAllowed = isOrder && createOnlySalesOrder;
	const showOnAccount = orderTypesAllowed && allowOnAccount;
	// Pro Forma is the Sales Partner flow only (the server refuses it for staff).
	const showProforma = isPartner && orderTypesAllowed && allowProforma;
	const showSubmitWithoutPayment = isPartner ? !showOnAccount && !showProforma : orderTypesAllowed;
	return { showSubmitWithoutPayment, showOnAccount, showProforma };
}

export type PartnerPaymentNote = {
	title: string;
	/** One explanation per available way to place the order. */
	lines: string[];
};

/**
 * Heading and explanation shown in the Sales Partner payment step. `__` is the translate
 * function, taken as an argument so the literals stay extractable and the helper stays pure.
 */
export function partnerPaymentNote(
	{ showSubmitWithoutPayment, showOnAccount, showProforma }: PaymentTypeOptions,
	__: (...args: [string]) => string,
): PartnerPaymentNote {
	if (!showOnAccount && !showProforma) {
		return {
			title: __("Place Order"),
			lines: [__("No payment is taken here. Agile will invoice this order.")],
		};
	}
	const lines: string[] = [];
	if (showProforma) {
		lines.push(
			__(
				"Pro Forma: a pro forma invoice with a payment link is emailed to the customer. The order is held until it is paid.",
			),
		);
	}
	if (showOnAccount) {
		lines.push(__("On Account: no payment is taken now. Agile will invoice this order."));
	}
	if (showSubmitWithoutPayment) {
		lines.push(__("No payment is taken here. Agile will invoice this order."));
	}
	return { title: __("How would you like to place this order?"), lines };
}
