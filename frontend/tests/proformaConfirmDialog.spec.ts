// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { defineComponent, h } from "vue";
import { flushPromises, mount } from "@vue/test-utils";

const fetchDefault = vi.fn();

vi.mock("../src/posapp/services/proformaService", async (importOriginal) => ({
	...(await importOriginal<any>()),
	fetchProformaDefaultRecipient: (...args: any[]) => fetchDefault(...args),
}));

import ProformaConfirmDialog from "../src/posapp/components/pos/payments/ProformaConfirmDialog.vue";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});
const ButtonStub = defineComponent({
	inheritAttrs: false,
	props: { disabled: Boolean },
	emits: ["click"],
	setup(props, { attrs, slots, emit }) {
		return () =>
			h(
				"button",
				{
					"data-testid": attrs["data-testid"],
					disabled: props.disabled,
					onClick: () => emit("click"),
				},
				slots.default?.(),
			);
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
				h("span", { "data-testid": "error" }, (props.errorMessages as string[]).join(" ")),
			]);
	},
});
const AlertStub = defineComponent({
	setup(_, { attrs, slots }) {
		return () => h("div", { "data-testid": attrs["data-testid"] }, slots.default?.());
	},
});

const mountDialog = (onConfirm = vi.fn(), onClose = vi.fn()) => {
	const wrapper = mount(ProformaConfirmDialog, {
		props: {
			modelValue: true,
			customer: "CUST-A",
			customerName: "Acme",
			onConfirm,
			"onUpdate:modelValue": onClose,
		},
		global: {
			components: {
				VDialog: BoxStub,
				VCard: BoxStub,
				VCardTitle: BoxStub,
				VCardText: BoxStub,
				VCardActions: BoxStub,
				VProgressCircular: BoxStub,
				VAlert: AlertStub,
				VTextField: TextFieldStub,
				VBtn: ButtonStub,
			},
		},
	});
	return { wrapper, onConfirm, onClose };
};

const input = (w: any) => w.find('[data-testid="proforma-confirm-recipient"]');
const submit = (w: any) => w.find('[data-testid="proforma-confirm-submit"]');

describe("ProformaConfirmDialog", () => {
	beforeEach(() => {
		fetchDefault.mockReset();
		const tr = (v: string, a?: any[]) =>
			a?.length ? v.replace(/\{(\d+)\}/g, (_m, i) => String(a[Number(i)] ?? "")) : v;
		vi.stubGlobal("__", tr);
		(window as any).__ = tr;
	});

	it("asks for the customer's default and prefills the field", async () => {
		fetchDefault.mockResolvedValue({ recipient: "invoice@x.example", devSiteOverride: false, ok: true });
		const { wrapper } = mountDialog();
		await flushPromises();

		expect(fetchDefault).toHaveBeenCalledWith("CUST-A");
		expect((input(wrapper).element as HTMLInputElement).value).toBe("invoice@x.example");
		expect(submit(wrapper).attributes("disabled")).toBeUndefined();
		expect(wrapper.find('[data-testid="proforma-confirm-dev"]').exists()).toBe(false);
	});

	it("confirm emits the (edited) address and nothing else", async () => {
		fetchDefault.mockResolvedValue({ recipient: "invoice@x.example", devSiteOverride: false, ok: true });
		const { wrapper, onConfirm } = mountDialog();
		await flushPromises();

		await input(wrapper).setValue("  other@y.example ");
		await submit(wrapper).trigger("click");
		expect(onConfirm).toHaveBeenCalledTimes(1);
		expect(onConfirm).toHaveBeenCalledWith("other@y.example");
	});

	it("blocks an invalid address with a message and confirms nothing", async () => {
		fetchDefault.mockResolvedValue({ recipient: "invoice@x.example", devSiteOverride: false, ok: true });
		const { wrapper, onConfirm } = mountDialog();
		await flushPromises();

		for (const bad of ["not-an-email", "a@b.example, c@d.example"]) {
			await input(wrapper).setValue(bad);
			expect(wrapper.find('[data-testid="error"]').text()).toContain("Enter a valid email address");
			expect(submit(wrapper).attributes("disabled")).toBeDefined();
			await submit(wrapper).trigger("click");
		}
		expect(onConfirm).not.toHaveBeenCalled();
	});

	it("forces an address to be typed when none is on file", async () => {
		fetchDefault.mockResolvedValue({ recipient: "", devSiteOverride: false, ok: true });
		const { wrapper, onConfirm } = mountDialog();
		await flushPromises();

		expect(wrapper.find('[data-testid="error"]').text()).toContain("Enter the email address");
		expect(submit(wrapper).attributes("disabled")).toBeDefined();
		await input(wrapper).setValue("new@x.example");
		await submit(wrapper).trigger("click");
		expect(onConfirm).toHaveBeenCalledWith("new@x.example");
	});

	it("a failed lookup warns and still requires an address", async () => {
		fetchDefault.mockResolvedValue({ recipient: "", devSiteOverride: false, ok: false });
		const { wrapper } = mountDialog();
		await flushPromises();

		expect(wrapper.find('[data-testid="proforma-confirm-lookup-failed"]').exists()).toBe(true);
		expect(submit(wrapper).attributes("disabled")).toBeDefined();
	});

	it("says where mail goes on a dev site", async () => {
		fetchDefault.mockResolvedValue({ recipient: "dev@example.com", devSiteOverride: true, ok: true });
		const { wrapper } = mountDialog();
		await flushPromises();

		expect(wrapper.find('[data-testid="proforma-confirm-dev"]').text()).toBe("Dev site: emails go to dev@example.com");
	});

	it("Cancel closes the dialog and confirms nothing", async () => {
		fetchDefault.mockResolvedValue({ recipient: "invoice@x.example", devSiteOverride: false, ok: true });
		const { wrapper, onConfirm, onClose } = mountDialog();
		await flushPromises();

		await wrapper.find('[data-testid="proforma-confirm-cancel"]').trigger("click");
		expect(onClose).toHaveBeenCalledWith(false);
		expect(onConfirm).not.toHaveBeenCalled();
	});

	it("does not confirm while the lookup is still running", async () => {
		fetchDefault.mockReturnValue(new Promise(() => undefined));
		const { wrapper, onConfirm } = mountDialog();
		await flushPromises();

		expect(submit(wrapper).attributes("disabled")).toBeDefined();
		await submit(wrapper).trigger("click");
		expect(onConfirm).not.toHaveBeenCalled();
	});
});
