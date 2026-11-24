// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

// Kept apart from salesOrderManagementView.spec.ts, which needs a Vuetify install to mount.
vi.mock("vuetify", () => ({
	useDisplay: () => ({ lgAndUp: { value: true }, xs: { value: false } }),
}));
vi.mock("../src/posapp/services/api", () => ({ default: { call: vi.fn() } }));
vi.mock("../src/posapp/components/pos/items/ItemsSelector.vue", () => ({
	default: defineComponent({ name: "ItemsSelectorStub", setup: () => () => h("div") }),
}));
const toastShow = vi.fn();
vi.mock("../src/posapp/stores/toastStore.js", () => ({ useToastStore: () => ({ show: toastShow }) }));
vi.mock("vue-router", () => ({
	useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
	useRoute: () => ({ query: {} }),
}));
const offline = { value: false };
vi.mock("../src/offline/index", () => ({ isOffline: () => offline.value }));

import SalesOrderManagementView from "../src/posapp/components/pos/shell/SalesOrderManagementView.vue";
import api from "../src/posapp/services/api";
import { useUIStore } from "../src/posapp/stores/uiStore";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});
const BtnStub = defineComponent({
	emits: ["click"],
	setup(_, { attrs, slots, emit }) {
		return () =>
			h("button", { "data-testid": attrs["data-testid"], onClick: () => emit("click") }, slots.default?.());
	},
});
const ListItemStub = defineComponent({
	props: { title: { type: String, default: "" } },
	emits: ["click"],
	setup(props, { attrs, emit }) {
		return () => h("button", { "data-testid": attrs["data-testid"], onClick: () => emit("click") }, props.title);
	},
});
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
				h("span", { "data-testid": `${attrs["data-testid"]}-error` }, (props.errorMessages as string[]).join(" ")),
			]);
	},
});
const DialogStub = defineComponent({
	props: { modelValue: { type: Boolean, default: false } },
	setup(props, { slots }) {
		return () => (props.modelValue ? h("div", {}, slots.default?.()) : null);
	},
});

const flush = async () => {
	for (let i = 0; i < 4; i++) await Promise.resolve();
	await new Promise((resolve) => setTimeout(resolve, 0));
};

const detail = (type: string, status = "To Deliver") => ({
	name: "SO-1",
	customer: "C",
	customer_name: "Test Customer",
	status,
	currency: "GBP",
	grand_total: 100,
	outstanding_balance: 100,
	posa_payment_type: type,
	proforma_recipient: type === "Proforma" ? "invoice@x.example" : "",
	items: [],
});

const mockOrders = (type: string, status?: string) =>
	(api.call as any).mockImplementation(async (method: string) => {
		if (method.endsWith("get_managed_sales_orders")) {
			return [{ name: "SO-1", customer_name: "Test Customer", currency: "GBP", posa_payment_type: type }];
		}
		if (method.endsWith("get_managed_sales_order")) return detail(type, status);
		return null;
	});

const mountView = () =>
	mount(SalesOrderManagementView, {
		global: {
			mocks: { __: (v: string) => v },
			components: {
				VContainer: BoxStub, VRow: BoxStub, VCol: BoxStub, VCard: BoxStub, VCardTitle: BoxStub,
				VCardText: BoxStub, VCardActions: BoxStub, VAlert: BoxStub, VBtn: BtnStub, VTable: BoxStub,
				VDialog: DialogStub, VSelect: BoxStub, VTextField: TextFieldStub, VTextarea: BoxStub,
				VCheckbox: BoxStub, VueDatePicker: BoxStub, VNavigationDrawer: BoxStub,
				VMenu: BoxStub, VList: BoxStub, VListItem: ListItemStub, VChip: BoxStub,
			},
		},
	});

const asPartner = (call?: any) => {
	(globalThis as any).frappe = {
		_: (v: string) => v,
		boot: { posa_partner_mode: { partners: ["SP-A"] } },
		call,
	};
};

describe("SalesOrderManagementView pro forma", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		vi.clearAllMocks();
		offline.value = false;
		vi.stubGlobal("__", (v: string) => v);
		(globalThis as any).frappe = { _: (v: string) => v };
		useUIStore().setPosProfile({
			name: "Main POS", company: "Test Company", currency: "GBP", custom_allow_select_sales_order: 1, payments: [{ mode_of_payment: "Cash" }],
		} as any);
	});

	const sentOk = (extra: Record<string, any> = {}) =>
		vi.fn((opts: any) =>
			opts.callback({ message: { ok: true, email_sent: true, attachment_ok: true, ...extra } }),
		);

	it("shows the type in the list and lets a partner resend to the prefilled default, via a POST send_proforma with resend", async () => {
		const call = sentOk({ recipient: "invoice@x.example" });
		asPartner(call);
		mockOrders("Proforma");
		const wrapper = mountView();
		await flush();

		expect(wrapper.find('[data-testid="order-payment-type"]').text()).toBe("Pro Forma");
		await wrapper.find('[data-testid="resend-proforma"]').trigger("click");
		const field = wrapper.find('[data-testid="proforma-resend-email"]');
		expect((field.element as HTMLInputElement).value).toBe("invoice@x.example");
		expect(call).not.toHaveBeenCalled(); // opening the dialog sends nothing
		await wrapper.find('[data-testid="proforma-resend-send"]').trigger("click");
		await flush();

		expect(call.mock.calls[0][0]).toMatchObject({
			method: "posawesome.posawesome.api.sales_orders.send_proforma",
			type: "POST",
			args: { sales_order: "SO-1", resend: 1, recipient: "invoice@x.example" },
		});
		expect(toastShow).toHaveBeenCalledWith(expect.objectContaining({ color: "success" }));
	});

	it("sends to the address typed in the Resend Pro Forma dialog", async () => {
		const call = sentOk({ recipient: "other@y.example" });
		asPartner(call);
		mockOrders("Proforma");
		const wrapper = mountView();
		await flush();

		await wrapper.find('[data-testid="resend-proforma"]').trigger("click");
		await wrapper.find('[data-testid="proforma-resend-email"]').setValue(" other@y.example ");
		await wrapper.find('[data-testid="proforma-resend-send"]').trigger("click");
		await flush();

		expect(call.mock.calls[0][0].args).toMatchObject({ resend: 1, recipient: "other@y.example" });
	});

	it("blocks an invalid address in the Resend Pro Forma dialog with a message", async () => {
		const call = sentOk();
		asPartner(call);
		mockOrders("Proforma");
		const wrapper = mountView();
		await flush();

		await wrapper.find('[data-testid="resend-proforma"]').trigger("click");
		await wrapper.find('[data-testid="proforma-resend-email"]').setValue("a@b.example, c@d.example");
		await wrapper.find('[data-testid="proforma-resend-send"]').trigger("click");
		await flush();

		expect(call).not.toHaveBeenCalled();
		expect(wrapper.find('[data-testid="proforma-resend-email-error"]').text()).toContain(
			"Enter a valid email address",
		);
	});

	it("reports an unsent pro forma as a warning, not a success", async () => {
		asPartner(vi.fn((opts: any) => opts.callback({ message: { ok: true, email_sent: false, error: "No email" } })));
		mockOrders("Proforma");
		const wrapper = mountView();
		await flush();
		await wrapper.find('[data-testid="resend-proforma"]').trigger("click");
		await wrapper.find('[data-testid="proforma-resend-send"]').trigger("click");
		await flush();
		expect(toastShow).toHaveBeenCalledWith(expect.objectContaining({ color: "warning" }));
	});

	it("does not call the server while offline", async () => {
		const call = vi.fn();
		asPartner(call);
		offline.value = true;
		mockOrders("Proforma");
		const wrapper = mountView();
		await flush();
		await wrapper.find('[data-testid="resend-proforma"]').trigger("click");
		expect(call).not.toHaveBeenCalled();
		expect(toastShow).toHaveBeenCalledWith(expect.objectContaining({ color: "warning" }));
	});

	it("gives staff no resend button and no manual receipt for a pro forma order", async () => {
		mockOrders("Proforma");
		const wrapper = mountView();
		await flush();
		expect(wrapper.find('[data-testid="resend-proforma"]').exists()).toBe(false);
		expect(wrapper.text()).not.toContain("Email Receipt");
	});

	it("keeps Email Receipt for staff on an ordinary order and shows On Account", async () => {
		mockOrders("On Account");
		const wrapper = mountView();
		await flush();
		expect(wrapper.text()).toContain("Email Receipt");
		expect(wrapper.find('[data-testid="order-payment-type"]').text()).toBe("On Account");
		expect(wrapper.find('[data-testid="resend-proforma"]').exists()).toBe(false);
	});

	it("offers no resend once the order is cancelled", async () => {
		asPartner(vi.fn());
		mockOrders("Proforma", "Cancelled");
		const wrapper = mountView();
		await flush();
		expect(wrapper.find('[data-testid="resend-proforma"]').exists()).toBe(false);
	});
});
