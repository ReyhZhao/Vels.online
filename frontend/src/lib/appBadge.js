// Mirror the unread notification count to the OS app-icon badge (the home-screen
// counter on an installed PWA). Feature-detected via the Badging API; a silent
// no-op on browsers/devices without it or when the app is not installed.
export function syncAppBadge(count) {
  if (typeof navigator === 'undefined' || !('setAppBadge' in navigator)) return;
  if (typeof count === 'number' && count > 0) {
    navigator.setAppBadge(count).catch(() => {});
  } else {
    navigator.clearAppBadge().catch(() => {});
  }
}
