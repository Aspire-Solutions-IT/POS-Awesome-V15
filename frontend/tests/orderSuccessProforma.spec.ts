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
				VBtn: ButtonStub,
			},
		},
	});

const ok = { ok: true, link: "https://pay/x", emailSent: true, attachmentOk: true, error: "" };

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
		expect(sendProforma).toHaveBeenCalledWith("SO-1", { resend: false });
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

		expect(sendProforma).toHaveBeenLastCalledWith("SO-1", { resend: true });
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
});
