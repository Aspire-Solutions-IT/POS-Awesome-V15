import { onBeforeUnmount, onMounted, watch } from "vue";
import { useEmployeeStore } from "../../stores/employeeStore";

const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "touchstart", "wheel", "scroll"] as const;
const CHECK_INTERVAL_MS = 10_000;

/**
 * Auto-locks the POS terminal after a period of no user activity, mirroring
 * the manual "lock_pos_screen" shortcut. Uses a timestamp + polling interval
 * rather than resetting a setTimeout on every event, since activity events
 * (mousemove in particular) can fire far more often than the lock check needs.
 */
export function useInactivityLock(timeoutMs = 5 * 60 * 1000, isEnabled: () => boolean = () => true) {
	const employeeStore = useEmployeeStore();
	let lastActivityAt = Date.now();
	let intervalId: ReturnType<typeof setInterval> | null = null;

	const recordActivity = () => {
		lastActivityAt = Date.now();
	};

	const checkInactivity = () => {
		if (employeeStore.isLocked || !isEnabled()) {
			return;
		}
		if (Date.now() - lastActivityAt >= timeoutMs) {
			employeeStore.lockTerminal();
		}
	};

	onMounted(() => {
		ACTIVITY_EVENTS.forEach((eventName) => {
			window.addEventListener(eventName, recordActivity, { passive: true });
		});
		intervalId = setInterval(checkInactivity, CHECK_INTERVAL_MS);
	});

	onBeforeUnmount(() => {
		ACTIVITY_EVENTS.forEach((eventName) => {
			window.removeEventListener(eventName, recordActivity);
		});
		if (intervalId) {
			clearInterval(intervalId);
			intervalId = null;
		}
	});

	// Restart the countdown fresh once the terminal is unlocked again.
	watch(
		() => employeeStore.isLocked,
		(locked) => {
			if (!locked) {
				recordActivity();
			}
		},
	);
}

export default useInactivityLock;
