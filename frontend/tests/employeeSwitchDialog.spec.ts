// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";

import EmployeeSwitchDialog from "../src/posapp/components/pos/employee/EmployeeSwitchDialog.vue";
import { useEmployeeStore } from "../src/posapp/stores/employeeStore";
import { useUIStore } from "../src/posapp/stores/uiStore";

const BoxStub = defineComponent({
	setup(_, { slots }) {
		return () => h("div", {}, slots.default?.());
	},
});

const VDialogStub = defineComponent({
	name: "VDialogStub",
	props: {
		modelValue: {
			type: Boolean,
			default: false,
		},
	},
	emits: ["update:modelValue"],
	setup(props, { slots }) {
		return () => (props.modelValue ? h("div", {}, slots.default?.()) : null);
	},
});

const VBtnStub = defineComponent({
	name: "VBtnStub",
	props: {
		disabled: {
			type: Boolean,
			default: false,
		},
	},
	emits: ["click"],
	setup(props, { attrs, slots, emit }) {
		return () =>
			h(
				"button",
				{
					type: "button",
					disabled: props.disabled,
					"data-test": attrs["data-test"],
					onClick: () => emit("click"),
				},
				slots.default?.(),
			);
	},
});

const VTextFieldStub = defineComponent({
	name: "VTextFieldStub",
	props: {
		modelValue: {
			type: [String, Number],
			default: "",
		},
		type: {
			type: String,
			default: "text",
		},
		appendInnerIcon: {
			type: String,
			default: "",
		},
		readonly: {
			type: Boolean,
			default: false,
		},
	},
	emits: ["update:modelValue", "click:append-inner"],
	setup(props, { attrs, emit }) {
		return () =>
			h("div", {}, [
				h("input", {
					value: props.modelValue,
					type: props.type,
					readonly: props.readonly,
					autocomplete: attrs.autocomplete,
					name: attrs.name,
					"data-lpignore": attrs["data-lpignore"],
					"data-1p-ignore": attrs["data-1p-ignore"],
					"data-bwignore": attrs["data-bwignore"],
					"data-test": attrs["data-test"],
					onPointerdown: attrs.onPointerdown as any,
					onKeydown: attrs.onKeydown as any,
					onPaste: attrs.onPaste as any,
					onInput: (event: Event) =>
						emit("update:modelValue", (event.target as HTMLInputElement).value),
				}),
				props.appendInnerIcon
					? h(
							"button",
							{
								type: "button",
								"data-test": `${attrs["data-test"]}-toggle`,
								onClick: () => emit("click:append-inner"),
							},
							props.appendInnerIcon,
						)
					: null,
			]);
	},
});

describe("EmployeeSwitchDialog", () => {
	beforeEach(() => {
		setActivePinia(createPinia());
		(window as any).__ = (value: string) => value;
		(window as any).frappe = {
			session: {
				user: "cashier@example.com",
				user_fullname: "Main Cashier",
			},
			call: vi.fn(async () => ({
				message: {
					user: "backup@example.com",
					full_name: "Backup Cashier",
					is_supervisor: false,
				},
			})),
		};
	});

	it("requires a cashier pin before switching terminal operator", async () => {
		const store = useEmployeeStore();
		const uiStore = useUIStore();
		uiStore.setPosProfile({ name: "Main POS" } as any);
		store.setTerminalEmployees([
			{ user: "cashier@example.com", full_name: "Main Cashier" },
			{ user: "backup@example.com", full_name: "Backup Cashier" },
		]);
		store.openEmployeeSwitch();

		const wrapper = mount(EmployeeSwitchDialog, {
			global: {
				components: {
					VDialog: VDialogStub,
					VCard: BoxStub,
					VCardTitle: BoxStub,
					VCardText: BoxStub,
					VCardActions: BoxStub,
					VBtn: VBtnStub,
					VIcon: BoxStub,
					VAlert: BoxStub,
					VTextField: VTextFieldStub,
				},
			},
		});

		await wrapper.get('[data-test="employee-option-backup@example.com"]').trigger("click");
		await wrapper.get('input[data-test="cashier-pin-input"]').setValue("1234");
		await wrapper.get('[data-test="cashier-pin-submit"]').trigger("click");
		await Promise.resolve();

		expect((window as any).frappe.call).toHaveBeenCalledWith({
			method: "posawesome.posawesome.api.employees.verify_terminal_employee_pin",
			args: {
				pos_profile: "Main POS",
				user: "backup@example.com",
				pin: "1234",
			},
		});
		expect(store.currentCashier?.user).toBe("backup@example.com");
		expect(store.switchDialogOpen).toBe(false);
	});

	it("blocks password-manager autofill until the cashier interacts with the PIN field", async () => {
		const store = useEmployeeStore();
		store.setTerminalEmployees([
			{ user: "cashier@example.com", full_name: "Main Cashier" },
		]);
		store.openEmployeeSwitch();

		const wrapper = mount(EmployeeSwitchDialog, {
			global: {
				components: {
					VDialog: VDialogStub,
					VCard: BoxStub,
					VCardTitle: BoxStub,
					VCardText: BoxStub,
					VCardActions: BoxStub,
					VBtn: VBtnStub,
					VIcon: BoxStub,
					VAlert: BoxStub,
					VTextField: VTextFieldStub,
				},
			},
		});

		const pinInput = wrapper.get('input[data-test="cashier-pin-input"]');
		expect(pinInput.attributes("autocomplete")).toBe("new-password");
		expect(pinInput.attributes("name")).toBe("posa-terminal-access-code");
		expect(pinInput.attributes("data-lpignore")).toBe("true");
		expect(pinInput.attributes("data-1p-ignore")).toBeDefined();
		expect(pinInput.attributes("data-bwignore")).toBeDefined();
		expect(pinInput.attributes("readonly")).toBeDefined();

		await pinInput.trigger("pointerdown");
		expect(pinInput.attributes("readonly")).toBeUndefined();

		store.lockTerminal();
		await wrapper.vm.$nextTick();
		await wrapper.get('[data-test="unlock-employee-option-cashier@example.com"]').trigger("click");
		const unlockPinInput = wrapper.get('input[data-test="cashier-unlock-pin-input"]');
		expect(unlockPinInput.attributes("autocomplete")).toBe("new-password");
		expect(unlockPinInput.attributes("name")).toBe("posa-terminal-unlock-code");
		expect(unlockPinInput.attributes("data-lpignore")).toBe("true");
		expect(unlockPinInput.attributes("readonly")).toBeDefined();

		await unlockPinInput.trigger("pointerdown");
		expect(unlockPinInput.attributes("readonly")).toBeUndefined();
	});

	it("shows an actionable error state and allows revealing the PIN", async () => {
		const store = useEmployeeStore();
		const uiStore = useUIStore();
		uiStore.setPosProfile({ name: "Main POS" } as any);
		store.setTerminalEmployees([
			{ user: "cashier@example.com", full_name: "Main Cashier" },
			{ user: "backup@example.com", full_name: "Backup Cashier" },
		]);
		store.openEmployeeSwitch();

		(window as any).frappe.call = vi.fn(async () => {
			throw new Error("Invalid cashier PIN.");
		});

		const wrapper = mount(EmployeeSwitchDialog, {
			global: {
				components: {
					VDialog: VDialogStub,
					VCard: BoxStub,
					VCardTitle: BoxStub,
					VCardText: BoxStub,
					VCardActions: BoxStub,
					VBtn: VBtnStub,
					VIcon: BoxStub,
					VAlert: BoxStub,
					VTextField: VTextFieldStub,
				},
			},
		});

		await wrapper.get('[data-test="employee-option-backup@example.com"]').trigger("click");
		expect(wrapper.get('input[data-test="cashier-pin-input"]').attributes("type")).toBe("password");

		await wrapper.get('[data-test="cashier-pin-input-toggle"]').trigger("click");
		expect(wrapper.get('input[data-test="cashier-pin-input"]').attributes("type")).toBe("text");

		await wrapper.get('input[data-test="cashier-pin-input"]').setValue("9999");
		await wrapper.get('[data-test="cashier-pin-submit"]').trigger("click");
		await Promise.resolve();

		expect(wrapper.get('[data-test="cashier-pin-error"]').text()).toContain("Invalid cashier PIN.");
		expect(wrapper.text()).toContain("Set each cashier PIN in the User form");
	});
});
