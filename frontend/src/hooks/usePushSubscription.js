import { useState, useEffect } from 'react';
import api from '../lib/axios';

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

export default function usePushSubscription() {
  const isSupported = typeof window !== 'undefined' && 'PushManager' in window && 'serviceWorker' in navigator;
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [publicKey, setPublicKey] = useState(null);
  const [loading, setLoading] = useState(false);
  const [keyError, setKeyError] = useState(false);

  useEffect(() => {
    if (!isSupported) return;
    api.get('/api/me/push/vapid-public-key/')
      .then(res => setPublicKey(res.data.public_key))
      .catch(() => setKeyError(true));
    navigator.serviceWorker.ready.then(reg =>
      reg.pushManager.getSubscription().then(sub => setIsSubscribed(!!sub))
    ).catch(() => {});
  }, [isSupported]);

  async function subscribe() {
    if (!isSupported) return;
    if (!publicKey) throw new Error('Push notifications are not available. Please try again later.');
    setLoading(true);
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') throw new Error('Permission denied');
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });
      const json = sub.toJSON();
      await api.post('/api/me/push/subscribe/', {
        endpoint: json.endpoint,
        p256dh: json.keys.p256dh,
        auth: json.keys.auth,
      });
      setIsSubscribed(true);
    } finally {
      setLoading(false);
    }
  }

  async function unsubscribe() {
    if (!isSupported) return;
    setLoading(true);
    try {
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.getSubscription();
      if (sub) {
        await api.delete('/api/me/push/subscribe/', { data: { endpoint: sub.endpoint } });
        await sub.unsubscribe();
      }
      setIsSubscribed(false);
    } finally {
      setLoading(false);
    }
  }

  return { isSubscribed, isSupported, loading, keyError, subscribe, unsubscribe };
}
