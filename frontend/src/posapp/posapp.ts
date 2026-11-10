import { createApp } from "vue";
// @ts-ignore
import vuetify from "./plugins/vuetify";
import "@mdi/font/css/materialdesignicons.css";
import "@fontsource/roboto/100.css";
import "@fontsource/roboto/300.css";
import "@fontsource/roboto/400.css";
import "@fontsource/roboto/500.css";
import "@fontsource/roboto/700.css";
import "@fontsource/roboto/900.css";
// @ts-ignore
import Dexie from "dexie/dist/dexie.mjs";
import VueDatePicker from "@vuepic/vue-datepicker";
import "@vuepic/vue-datepicker/dist/main.css";
import "../../../posawesome/public/css/rtl.css";
import "../style.css";
import "./styles/theme.css";
import eventBus from "./bus";
import themePlugin from "./plugins/theme";
import { pinia } from "./stores";
import { useToastStore } from "./stores/toastStore";
import { useSocketStore } from "./stores/socketStore";
import { useEmployeeStore } from "./stores/employeeStore";
import {
	installPartnerCallGuard,
	isPartnerMode,
	setPartnerCustomerProvider,
} from "./utils/partnerMode";
import { useCustomersStore } from "./stores/customersStore";
import { purgeBrowserCachesForPartner } from "./utils/partnerCaches";
import { createPosAppRouter } from "./router";
import {
	installGlobalErrorHandlers,
	isBenignGlobalError,
} from "./utils/errorReporting";
import {
	clearChunkRecoveryState,
	isDynamicImportFailure,
	recoverFromChunkLoadError,
	scheduleAfterStableBoot,
	scheduleChunkRecoveryStateReset,
} from "./utils/chunkLoadRecovery";
import { finalizePendingBundleActivation } from "./utils/bundleVersionActivation";
import { reconcileBuildChangeOnStartup } from "./utils/buildCacheReconciler";
import { initPromise, isOffline } from "../offline";
import "../sw-updater"; // Initialize service worker auto-updater
import App from "./App.vue";
// @ts-ignore
import {
	attachProfilerHelpers,
	initLongTaskObserver,
	isPerfEnabled,
} from "./utils/perf.js";

declare const __BUILD_VERSION__: string;

attachProfilerHelpers();

// Expose Dexie globally for libraries that expect a global Dexie instance
if (typeof window !== "undefined" && !(window as any).Dexie) {
	(window as any).Dexie = Dexie;
}

if (typeof frappe === "undefined") {
	console.error("Frappe is not defined");
} else {
	frappe.provide("frappe.PosApp");
}

frappe.PosApp.posapp = class {
	$parent: any;
	page: any;
	app: any;
	router: any;
	routerHistory: any;
	$el: any;

	constructor({ parent }: { parent: any }) {
		this.$parent = $(document);
		this.page = parent?.page || parent;
		this.app = null;
		this.make_body();
	}

	make_body() {
		this.$el = this.$parent.find(".main-section");
		void this.initializeApp();
	}

	async initializeApp() {
		const buildVersion =
			typeof __BUILD_VERSION__ !== "undefined" ? __BUILD_VERSION__ : null;

		// A Sales Partner is confined to the POS: silence every call the server would
		// refuse, and start from empty read caches (a previous staff session may have
		// left prices and cost data behind).
		if (isPartnerMode()) {
			installPartnerCallGuard();
		}

		try {
			await initPromise;
			if (isPartnerMode()) {
				await purgeBrowserCachesForPartner();
			}
			await reconcileBuildChangeOnStartup({
				runtimeBuildVersion: buildVersion,
				isOnline: !isOffline(),
			});
		} catch (error) {
			console.error("Failed to reconcile build caches before POS app mount", error);
		}

		// Vuetify instance is now imported from plugins/vuetify.ts
		this.app = createApp(App);
		const { router, history } = createPosAppRouter();
		this.router = router;
		this.routerHistory = history;
		this.app.component("VueDatePicker", VueDatePicker);
		this.app.use(pinia);
		if (isPartnerMode()) {
			// Partners have no cashier PIN; clear any lock a shared browser left behind.
			useEmployeeStore().unlockTerminal();
			// Calls that need a customer get the one the partner has selected.
			setPartnerCustomerProvider(() => useCustomersStore().selectedCustomer || null);
		}
		this.app.use(this.router);
		this.app.use(eventBus);
		this.app.use(vuetify);
		this.app.use(themePlugin, { vuetify });

		this.app.config.errorHandler = (
			err: any,
			_instance: any,
			info: string,
		) => {
			if (isDynamicImportFailure(err)) {
				void recoverFromChunkLoadError(err, "vue-error-handler");
				return;
			}

			if (!isBenignGlobalError(err)) {
				console.error("Global Error:", err, info);
				const toastStore = useToastStore();
				toastStore.show({
					message: `An unexpected error occurred: ${err?.message || err}`,
					color: "error",
					timeout: 5000,
				});
			}
		};

		installGlobalErrorHandlers(this.app);

		this.app.mount(this.$el[0]);
		clearChunkRecoveryState();
		void this.router.isReady().finally(() => {
			scheduleChunkRecoveryStateReset();
			scheduleAfterStableBoot(() => {
				void finalizePendingBundleActivation();
			});
		});

		// Initialize socket listeners
		const socketStore = useSocketStore();
		socketStore.init();

		if (isPerfEnabled()) {
			initLongTaskObserver("posapp");
		}

		if (!document.querySelector('link[rel="manifest"]')) {
			const link = document.createElement("link");
			link.rel = "manifest";
			link.href = "/manifest.json";
			document.head.appendChild(link);
		}

		if (
			("serviceWorker" in navigator &&
				window.location.protocol === "https:") ||
			window.location.hostname === "localhost" ||
			window.location.hostname === "127.0.0.1"
		) {
			navigator.serviceWorker
				.register("/sw.js")
				.then((registration) => {
					console.log("SW registered successfully", registration);
				})
				.catch((err) => console.error("SW registration failed", err));
		}
	}

	unmount() {
		if (this.app) {
			// Clean up router to prevent global navigation interference
			if (this.router) {
				// Remove all route guards and listeners
				this.router.beforeEachCbs = [];
				this.router.afterEachCbs = [];
			}

			if (
				this.routerHistory &&
				typeof this.routerHistory.destroy === "function"
			) {
				this.routerHistory.destroy();
			} else if (
				this.router &&
				this.router.options &&
				this.router.options.history &&
				typeof this.router.options.history.destroy === "function"
			) {
				this.router.options.history.destroy();
			}

			this.app.unmount();
			this.app = null;
			this.router = null;
			this.routerHistory = null;
			console.info("POS App unmounted");
		}
	}

	setup_header() {}
};
