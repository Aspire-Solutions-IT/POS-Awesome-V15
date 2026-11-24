// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h, nextTick } from "vue";
import { flushPromises, mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

const sendProforma = vi.fn();

vi.mock("../src/posapp/services/proformaService", async (importOriginal) => ({
	...(await importOriginal<any>()),
	sendProforma: (...args: any[]) => sendProforma(...args),
}));
// The dialog imports the store by its .js name, which only the bundler resolves to uiStore.ts.
vi.mock("../src/posapp/stores/uiStore", async () => {
	const { defineStore } = await import("pinia");
	const { ref } = await import("vue");
	return {
		useUIStore: defineStore("uiStoreTest", () => {
			const orderSuccess = ref<any>(null);
			return {
				orderSuccess,
				showOrderSuccess: (payload: any) => (orderSuccess.value = payload),
				closeOrderSuccess: () => (orderSuccess.value = null),
			};
		}),
	};
});
vi.mock("vue-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("../src/posapp/format", () => ({
	useFormat: () => ({ formatCurrency: (v: any) => String(v), currencySymbol: () => "" }),
}));
vi.mock("../src/posapp/utils/receiptPdfUrl", () => ({ openReceiptPdf: vi.fn() }));

import OrderSuccessDialog from "../src/posapp/components/pos/payments/OrderSuccessDialog.vue";
import { useUIStore } from "../src/posapp/stores/uiStore";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});
const ButtonStub = defineComponent({
	emits: ["click"],
	setup(_, { attrs, slots, emit }) {
		return () =>
			h("button", { "data-testid": attrs["data-testid"], onClick: () => emit("click") }, slots.default?.());
	},
});
// Renders the field's value and error text; typing is simulated through the input's events.
const TextFieldStub = defineComponent({
	inheritAttrs: false,
	props: { modelValue: { type: String, default: "" }, errorMessages: { type: Array, default: () => [] } },
	emits: ["update:modelValue"],
	setup(props, { attrs, emit }) {
		return () =>
			h("div", {}, [
				h("input", {
					"data-testid": attrs["data-testid"],
					value: props.modelValue,
					onInput: (event: any) => emit("update:modelValue", event.target.value),
				}),
				h("span", { "data-testid": "recipient-error" }, (props.errorMessages as string[]).join(" ")),
			]);
	},
});
const AlertStub = defineComponent({
	setup(_, { attrs, slots }) {
		return () => h("div", { "data-testid": attrs["data-testid"] }, slots.default?.());
	},
});

const mountDialog = () =>
	mount(OrderSuccessDialog, {
		global: {
			components: {
				VDialog: BoxStub,
				VCard: BoxStub,
				VCardText: BoxStub,
				VCardActions: BoxStub,
				VIcon: BoxStub,
				VProgressCircular: BoxStub,
				VAlert: AlertStub,
				VTextField: TextFieldStub,
				VBtn: ButtonStub,
			},
		},
	});

const ok = {
	ok: true,
	link: "https://pay/x",
	emailSent: true,
	attachmentOk: true,
	error: "",
	inProgress: false,
	recipient: "",
	recipientDefault: "",
};

describe("OrderSuccessDialog pro forma", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		sendProforma.mockReset();
		const tr = (v: string, a?: any[]) =>
			a?.length ? v.replace(/\{(\d+)\}/g, (_m, i) => String(a[Number(i)] ?? "")) : v;
		vi.stubGlobal("__", tr);
		(window as any).__ = tr;
		vi.stubGlobal("frappe", { boot: { posa_partner_mode: { partners: [] } }, call: vi.fn(() => Promise.resolve({})) });
	});

	const open = (paymentType: string) =>
		useUIStore().showOrderSuccess({ orders: ["SO-1"], profile: {}, noPayment: true, paymentType });

	it("sends the pro forma once and shows success without a retry button", async () => {
		sendProforma.mockResolvedValue(ok);
		open("Proforma");
		const wrapper = mountDialog();
		await flushPromises();

		expect(sendProforma).toHaveBeenCalledTimes(1);
		expect(sendProforma).toHaveBeenCalledWith("SO-1", { resend: false, recipient: "" });
		expect(wrapper.text()).toContain("Pro Forma Order Placed");
		expect(wrapper.find('[data-testid="proforma-outcome"]').text()).toContain("emailed");
		expect(wrapper.find('[data-testid="proforma-retry"]').exists()).toBe(false);
		expect(wrapper.text()).not.toContain("Send Payment Link");
	});

	it("on failure says the order is saved and Retry resends", async () => {
		sendProforma.mockResolvedValueOnce({ ...ok, ok: false, link: "", emailSent: false, error: "" });
		open("Proforma");
		const wrapper = mountDialog();
		await flushPromises();

		expect(wrapper.find('[data-testid="proforma-outcome"]').text()).toContain("order was saved");
		sendProforma.mockResolvedValueOnce(ok);
		await wrapper.find('[data-testid="proforma-retry"]').trigger("click");
		await flushPromises();

		expect(sendProforma).toHaveBeenLastCalledWith("SO-1", { resend: true, recipient: "" });
		expect(wrapper.find('[data-testid="proforma-retry"]').exists()).toBe(false);
	});

	it("shows the link-only and missing-attachment states with a Resend button", async () => {
		sendProforma.mockResolvedValueOnce({ ...ok, emailSent: false, error: "No email" });
		open("Proforma");
		const wrapper = mountDialog();
		await flushPromises();
		expect(wrapper.find('[data-testid="proforma-outcome"]').text()).toContain("No email");
		expect(wrapper.find('[data-testid="proforma-retry"]').text()).toBe("Resend Pro Forma");

		sendProforma.mockResolvedValueOnce({ ...ok, attachmentOk: false });
		await wrapper.find('[data-testid="proforma-retry"]').trigger("click");
		await flushPromises();
		expect(wrapper.find('[data-testid="proforma-outcome"]').text()).toContain("could not be attached");
	});

	it("does not call send_proforma for On Account", async () => {
		open("On Account");
		const wrapper = mountDialog();
		await nextTick();
		expect(sendProforma).not.toHaveBeenCalled();
		expect(wrapper.text()).toContain("Order Placed On Account");
		expect(wrapper.find('[data-testid="proforma-status"]').exists()).toBe(false);
	});

	describe("editable recipient", () => {
		const recipientInput = (wrapper: any) => wrapper.find('[data-testid="proforma-recipient"]');

		it("sends the first time to the confirmed address and hides the field until asked", async () => {
			sendProforma.mockResolvedValue({ ...ok, recipient: "typed@x.example", recipientDefault: "invoice@x.example" });
			useUIStore().showOrderSuccess({
				orders: ["SO-1"],
				profile: {},
				noPayment: true,
				paymentType: "Proforma",
				proformaRecipient: "typed@x.example",
			});
			const wrapper = mountDialog();
			await flushPromises();

			// one send, to the address confirmed before submit; nothing re-sends on open
			expect(sendProforma).toHaveBeenCalledTimes(1);
			expect(sendProforma).toHaveBeenCalledWith("SO-1", { resend: false, recipient: "typed@x.example" });
			// sent: no field and no send button, just the way to ask for them
			expect(recipientInput(wrapper).exists()).toBe(false);
			expect(wrapper.find('[data-testid="proforma-retry"]').exists()).toBe(false);

			await wrapper.find('[data-testid="proforma-change-recipient"]').trigger("click");
			expect((recipientInput(wrapper).element as HTMLInputElement).value).toBe("typed@x.example");
			expect(wrapper.find('[data-testid="proforma-retry"]').text()).toBe("Send");
			expect(wrapper.find('[data-testid="proforma-change-recipient"]').exists()).toBe(false);
		});

		it("resends to a new address after a successful send, then hides the field again", async () => {
			sendProforma.mockResolvedValueOnce({ ...ok, recipient: "first@x.example", recipientDefault: "first@x.example" });
			open("Proforma");
			const wrapper = mountDialog();
			await flushPromises();

			await wrapper.find('[data-testid="proforma-change-recipient"]').trigger("click");
			await recipientInput(wrapper).setValue("second@y.example");
			sendProforma.mockResolvedValueOnce({ ...ok, recipient: "second@y.example" });
			await wrapper.find('[data-testid="proforma-retry"]').trigger("click");
			await flushPromises();

			expect(sendProforma).toHaveBeenCalledTimes(2);
			expect(sendProforma).toHaveBeenLastCalledWith("SO-1", { resend: true, recipient: "second@y.example" });
			expect(wrapper.find('[data-testid="proforma-outcome"]').text()).toContain("second@y.example");
			expect(recipientInput(wrapper).exists()).toBe(false);
		});

		it("shows the field together with Retry when the first send failed", async () => {
			sendProforma.mockResolvedValueOnce({ ...ok, ok: false, link: "", emailSent: false, recipient: "a@x.example" });
			open("Proforma");
			const wrapper = mountDialog();
			await flushPromises();
			expect(recipientInput(wrapper).exists()).toBe(true);
			expect(wrapper.find('[data-testid="proforma-retry"]').exists()).toBe(true);
			expect(wrapper.find('[data-testid="proforma-change-recipient"]').exists()).toBe(false);
		});

		it("Retry sends to the address in the field", async () => {
			sendProforma.mockResolvedValueOnce({
				...ok,
				ok: false,
				link: "",
				emailSent: false,
				recipient: "invoice@x.example",
				recipientDefault: "invoice@x.example",
			});
			open("Proforma");
			const wrapper = mountDialog();
			await flushPromises();

			await recipientInput(wrapper).setValue(" other@y.example ");
			sendProforma.mockResolvedValueOnce({ ...ok, recipient: "other@y.example", recipientDefault: "invoice@x.example" });
			await wrapper.find('[data-testid="proforma-retry"]').trigger("click");
			await flushPromises();

			expect(sendProforma).toHaveBeenLastCalledWith("SO-1", { resend: true, recipient: "other@y.example" });
			// what the user typed is not overwritten by the server's default
			await wrapper.find('[data-testid="proforma-change-recipient"]').trigger("click");
			expect((recipientInput(wrapper).element as HTMLInputElement).value).toBe(" other@y.example ");
			expect(wrapper.find('[data-testid="proforma-outcome"]').text()).toContain("other@y.example");
		});

		it("blocks an invalid address with a message and sends nothing", async () => {
			sendProforma.mockResolvedValueOnce({ ...ok, ok: false, link: "", emailSent: false });
			open("Proforma");
			const wrapper = mountDialog();
			await flushPromises();
			sendProforma.mockClear();

			await recipientInput(wrapper).setValue("not-an-email");
			expect(wrapper.find('[data-testid="recipient-error"]').text()).toContain("Enter a valid email address");
			await wrapper.find('[data-testid="proforma-retry"]').trigger("click");
			await flushPromises();
			expect(sendProforma).not.toHaveBeenCalled();

			await recipientInput(wrapper).setValue("a@b.example, c@d.example");
			expect(wrapper.find('[data-testid="recipient-error"]').text()).toContain("Enter a valid email address");
		});
	});

	it("a slow answer for the previous order never shows in the next order's dialog", async () => {
		let releaseFirst: (_value: any) => void = () => undefined;
		sendProforma.mockImplementationOnce(() => new Promise((resolve) => (releaseFirst = resolve)));
		open("Proforma");
		const wrapper = mountDialog();
		await flushPromises();

		// the next order replaces the dialog before the first send has answered
		sendProforma.mockResolvedValueOnce({ ...ok, link: "https://pay/second", recipient: "second@x.example" });
		useUIStore().showOrderSuccess({
			orders: ["SO-2"],
			profile: {},
			noPayment: true,
			paymentType: "Proforma",
		});
		await flushPromises();
		expect(sendProforma).toHaveBeenLastCalledWith("SO-2", { resend: false, recipient: "" });

		releaseFirst({ ...ok, ok: false, link: "https://pay/first", emailSent: false, error: "first failed", recipient: "first@x.example" });
		await flushPromises();

		const text = wrapper.text();
		expect(text).not.toContain("first failed");
		await wrapper.find('[data-testid="proforma-change-recipient"]').trigger("click");
		expect(wrapper.find('[data-testid="proforma-recipient"]').exists()).toBe(true);
		expect((wrapper.find('[data-testid="proforma-recipient"]').element as HTMLInputElement).value).toBe(
			"second@x.example",
		);
		expect(wrapper.html()).not.toContain("https://pay/first");
		expect(wrapper.find('[data-testid="proforma-outcome"]').text()).toContain("emailed");
	});
});
