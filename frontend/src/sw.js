// Required by vite-plugin-pwa injectManifest strategy — plugin injects precache manifest here
self.__WB_MANIFEST;

// Set the OS app-icon badge (home-screen counter) to an absolute unread count.
// Feature-detected: a silent no-op where the Badging API is unavailable (desktop
// browsers, non-installed contexts, older iOS).
function syncAppBadge(count) {
  if (!('setAppBadge' in self.navigator) || typeof count !== 'number') {
    return Promise.resolve();
  }
  return count > 0
    ? self.navigator.setAppBadge(count).catch(() => {})
    : self.navigator.clearAppBadge().catch(() => {});
}

self.addEventListener('push', event => {
  const data = event.data?.json() ?? {};
  event.waitUntil(
    Promise.all([
      self.registration.showNotification(data.title ?? 'Vels Online', {
        body: data.body ?? '',
        icon: '/icons/icon-192.png',
        badge: '/icons/icon-192.png',
        data: { url: data.url ?? '/dashboard' },
      }),
      syncAppBadge(data.unread_count),
    ])
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(list => {
      const target = event.notification.data?.url ?? '/dashboard';
      const existing = list.find(c => c.url.includes(target) && 'focus' in c);
      if (existing) return existing.focus();
      return clients.openWindow(target);
    })
  );
});
