import { useState, useEffect } from 'react';
import { Bell, Mail } from 'lucide-react';
import api from '../../lib/axios';
import { useAuth } from '../../context/AuthContext';
import usePushSubscription from '../../hooks/usePushSubscription';

const CATEGORIES = [
  { key: 'assignment', label: 'Assignment', description: 'When an incident is assigned or transferred to you' },
  { key: 'delegation', label: 'Delegation', description: 'When an incident is delegated to you or returned' },
  { key: 'comment', label: 'Comments', description: 'When someone comments on an incident you are involved in' },
  { key: 'state_change', label: 'State changes', description: "When an incident's state changes" },
  { key: 'incident_alert', label: 'Incident alerts', description: 'High/critical severity incidents affecting your organisation' },
  { key: 'task_complete', label: 'Task completed', description: 'When an automated task assigned to your incident finishes' },
  { key: 'shift_swap', label: 'Shift swaps', description: 'When a shift swap or cover offer is sent to you' },
];

const GUARDRAIL_CATEGORIES = new Set(['assignment', 'delegation', 'shift_swap']);

function Toggle({ checked, onChange, disabled, label }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${
        checked ? 'bg-primary' : 'bg-muted'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
          checked ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  );
}

function EmailDiagnosticsSection() {
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  async function handleSend() {
    setSending(true);
    setResult(null);
    try {
      const res = await api.post('/api/admin/test-email/');
      setResult({ ok: true, message: res.data.detail });
    } catch (err) {
      setResult({ ok: false, message: err.response?.data?.detail || 'Failed to send test email.' });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mt-8">
      <h2 className="text-base font-semibold text-foreground mb-4 flex items-center gap-2">
        <Mail className="h-4 w-4 text-muted-foreground" />
        Email diagnostics
      </h2>
      <div className="rounded-lg border border-border p-4 space-y-3">
        <p className="text-sm text-muted-foreground">Send a test email to verify your email configuration is working correctly.</p>
        <button
          onClick={handleSend}
          disabled={sending}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {sending ? 'Sending…' : 'Send test email'}
        </button>
        {result && (
          <p className={`text-sm ${result.ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
            {result.message}
          </p>
        )}
      </div>
    </div>
  );
}

function PushDiagnosticsSection({ isSubscribed }) {
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);

  async function handleSend() {
    setSending(true);
    setResult(null);
    try {
      const res = await api.post('/api/me/push/test/');
      setResult({ ok: true, message: res.data.detail });
    } catch (err) {
      setResult({ ok: false, message: err.response?.data?.detail || 'Failed to send test push notification.' });
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mt-6">
      <h2 className="text-base font-semibold text-foreground mb-4 flex items-center gap-2">
        <Bell className="h-4 w-4 text-muted-foreground" />
        Push diagnostics
      </h2>
      <div className="rounded-lg border border-border p-4 space-y-3">
        <p className="text-sm text-muted-foreground">Send a test push notification to verify your push configuration is working correctly.</p>
        <button
          onClick={handleSend}
          disabled={sending || !isSubscribed}
          title={!isSubscribed ? 'Enable push notifications first' : undefined}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {sending ? 'Sending…' : 'Send test push'}
        </button>
        {!isSubscribed && (
          <p className="text-xs text-muted-foreground">Enable push notifications above before sending a test.</p>
        )}
        {result && (
          <p className={`text-sm ${result.ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
            {result.message}
          </p>
        )}
      </div>
    </div>
  );
}

export default function NotificationPreferences() {
  const { user } = useAuth();
  const { isSubscribed, isSupported, loading: pushLoading, subscribe, unsubscribe } = usePushSubscription();
  const [pushError, setPushError] = useState(null);

  const [prefs, setPrefs] = useState(null);
  const [pending, setPending] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [guardrailError, setGuardrailError] = useState(null);

  async function handleSubscribe() {
    setPushError(null);
    try {
      await subscribe();
    } catch (e) {
      setPushError(e.message === 'Permission denied' ? 'Notification permission was denied.' : 'Failed to enable push notifications.');
    }
  }

  useEffect(() => {
    api.get('/api/me/notification-prefs/').then(res => {
      setPrefs(res.data);
    });
  }, []);

  function effectiveValue(key) {
    if (key in pending) return pending[key];
    const defaultVal = key.startsWith('push_') ? false : true;
    return prefs?.[key] ?? defaultVal;
  }

  function handleToggle(key) {
    setGuardrailError(null);
    setSuccess(false);
    const category = key.replace(/^(email|inapp|push)_/, '');
    const newValue = !effectiveValue(key);

    if (GUARDRAIL_CATEGORIES.has(category) && !newValue) {
      if (category === 'shift_swap') {
        // shift_swap has 3 channels: email, inapp, push
        const channels = ['email', 'inapp', 'push'];
        const otherChannelsEnabled = channels
          .filter(ch => `${ch}_${category}` !== key)
          .some(ch => effectiveValue(`${ch}_${category}`));
        if (!otherChannelsEnabled) {
          setGuardrailError('At least one channel must remain enabled for shift swap notifications.');
          return;
        }
      } else {
        // Standard 2-channel guardrail
        const otherChannel = key.startsWith('email_') ? `inapp_${category}` : `email_${category}`;
        if (!effectiveValue(otherChannel)) {
          setGuardrailError(`At least one channel must remain enabled for ${category} notifications.`);
          return;
        }
      }
    }

    setPending(prev => ({ ...prev, [key]: newValue }));
  }

  async function handleSave() {
    if (Object.keys(pending).length === 0) return;
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const res = await api.patch('/api/me/notification-prefs/', pending);
      setPrefs(res.data);
      setPending({});
      setSuccess(true);
    } catch (err) {
      const detail = err.response?.data;
      setError(
        typeof detail === 'string'
          ? detail
          : JSON.stringify(detail) ?? 'Failed to save preferences.'
      );
    } finally {
      setSaving(false);
    }
  }

  if (!prefs) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-8">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    );
  }

  const hasPending = Object.keys(pending).length > 0;

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="text-2xl font-semibold text-foreground mb-1">Notification preferences</h1>
      <p className="text-sm text-muted-foreground mb-8">
        Choose which channels you want to receive notifications on.
      </p>

      {guardrailError && (
        <div
          role="alert"
          className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {guardrailError}
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {error}
        </div>
      )}

      {success && (
        <div
          role="status"
          className="mb-4 rounded-md border border-green-500/50 bg-green-500/10 px-4 py-3 text-sm text-green-700 dark:text-green-400"
        >
          Preferences saved.
        </div>
      )}

      {/* Push enrollment card */}
      <div className="mb-6 rounded-lg border border-border p-4 space-y-2">
        <p className="text-sm font-medium text-foreground">Push notifications</p>
        {!isSupported ? (
          <p className="text-sm text-muted-foreground">
            Push notifications are not supported in this browser. Install the app to your home screen to enable them.
          </p>
        ) : isSubscribed ? (
          <div className="flex items-center gap-3">
            <span className="text-sm text-green-600 dark:text-green-400 font-medium">Push notifications enabled</span>
            <button
              onClick={unsubscribe}
              disabled={pushLoading}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
            >
              Disable
            </button>
          </div>
        ) : (
          <div className="space-y-1">
            <button
              onClick={handleSubscribe}
              disabled={pushLoading}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
            >
              {pushLoading ? 'Enabling…' : 'Enable push notifications'}
            </button>
            {pushError && <p className="text-xs text-destructive">{pushError}</p>}
          </div>
        )}
      </div>

      <div className="rounded-lg border border-border overflow-hidden">
        <div className="grid grid-cols-[1fr_auto_auto_auto] gap-0">
          <div className="px-4 py-3 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Category
          </div>
          <div className="px-6 py-3 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide text-center">
            In-app
          </div>
          <div className="px-6 py-3 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide text-center">
            Email
          </div>
          <div className="px-6 py-3 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide text-center">
            Push
          </div>

          {CATEGORIES.map((cat, idx) => (
            <div key={cat.key} className="contents">
              <div
                className={`px-4 py-4 border-t border-border ${idx === 0 ? 'border-t' : ''}`}
              >
                <p className="text-sm font-medium text-foreground">{cat.label}</p>
                <p className="text-xs text-muted-foreground mt-0.5">{cat.description}</p>
              </div>
              <div className="px-6 py-4 border-t border-border flex items-center justify-center">
                <Toggle
                  checked={effectiveValue(`inapp_${cat.key}`)}
                  onChange={() => handleToggle(`inapp_${cat.key}`)}
                  label={`${cat.label} in-app`}
                />
              </div>
              <div className="px-6 py-4 border-t border-border flex items-center justify-center">
                <Toggle
                  checked={effectiveValue(`email_${cat.key}`)}
                  onChange={() => handleToggle(`email_${cat.key}`)}
                  label={`${cat.label} email`}
                />
              </div>
              <div className="px-6 py-4 border-t border-border flex items-center justify-center">
                <Toggle
                  checked={effectiveValue(`push_${cat.key}`)}
                  onChange={() => handleToggle(`push_${cat.key}`)}
                  disabled={!isSubscribed}
                  label={isSubscribed ? `${cat.label} push` : 'Enroll this device first'}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving || !hasPending}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {saving ? 'Saving…' : 'Save preferences'}
        </button>
      </div>

      {user?.is_staff && (
        <>
          <EmailDiagnosticsSection />
          <PushDiagnosticsSection isSubscribed={isSubscribed} />
        </>
      )}
    </div>
  );
}
