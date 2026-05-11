import { useState, useEffect } from 'react';
import api from '../../lib/axios';

const CATEGORIES = [
  { key: 'assignment', label: 'Assignment', description: 'When an incident is assigned or transferred to you' },
  { key: 'delegation', label: 'Delegation', description: 'When an incident is delegated to you or returned' },
  { key: 'comment', label: 'Comments', description: 'When someone comments on an incident you are involved in' },
  { key: 'state_change', label: 'State changes', description: "When an incident's state changes" },
  { key: 'incident_alert', label: 'Incident alerts', description: 'High/critical severity incidents affecting your organisation' },
];

const GUARDRAIL_CATEGORIES = new Set(['assignment', 'delegation']);

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

export default function NotificationPreferences() {
  const [prefs, setPrefs] = useState(null);
  const [pending, setPending] = useState({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [guardrailError, setGuardrailError] = useState(null);

  useEffect(() => {
    api.get('/api/me/notification-prefs/').then(res => {
      setPrefs(res.data);
    });
  }, []);

  function effectiveValue(key) {
    if (key in pending) return pending[key];
    return prefs?.[key] ?? true;
  }

  function handleToggle(key) {
    setGuardrailError(null);
    setSuccess(false);
    const category = key.replace(/^(email|inapp)_/, '');
    const otherChannel = key.startsWith('email_') ? `inapp_${category}` : `email_${category}`;
    const newValue = !effectiveValue(key);

    if (GUARDRAIL_CATEGORIES.has(category) && !newValue && !effectiveValue(otherChannel)) {
      setGuardrailError(`At least one channel must remain enabled for ${category} notifications.`);
      return;
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

      <div className="rounded-lg border border-border overflow-hidden">
        <div className="grid grid-cols-[1fr_auto_auto] gap-0">
          <div className="px-4 py-3 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide">
            Category
          </div>
          <div className="px-6 py-3 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide text-center">
            In-app
          </div>
          <div className="px-6 py-3 bg-muted/50 text-xs font-medium text-muted-foreground uppercase tracking-wide text-center">
            Email
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
    </div>
  );
}
