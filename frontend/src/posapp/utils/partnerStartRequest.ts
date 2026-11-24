import { ref } from "vue";

/** Set when a partner clicks the Customer box and wants to re-open the start dialog. */
export const partnerStartRequested = ref(false);
export const requestPartnerStart = () => {
	partnerStartRequested.value = true;
};
