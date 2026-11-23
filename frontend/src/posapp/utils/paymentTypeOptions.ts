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
