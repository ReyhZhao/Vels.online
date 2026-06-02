import { useState, useEffect } from 'react';
import { AlertTriangle } from 'lucide-react';
import api from '../lib/axios';
import { useAuth } from '../context/AuthContext';

function formatShiftEnd(utcString, timezone) {
  if (!utcString) return '';
  try {
    return new Date(utcString).toLocaleTimeString('en-US', {
      timeZone: timezone || 'Europe/Amsterdam',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch {
    return utcString;
  }
}

function initials(name) {
  if (!name) return '?';
  return name.split(' ').slice(0, 2).map(p => p[0].toUpperCase()).join('');
}

export function OnCallWidgetFull({ onHandOffNow }) {
  const { staffProfile } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/oncall/current/')
      .then(res => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        Loading on-call…
      </div>
    );
  }

  if (!data?.analyst) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-destructive" />
        <span className="text-sm font-medium text-destructive">No on-call analyst scheduled</span>
      </div>
    );
  }

  const tz = staffProfile?.timezone || 'Europe/Amsterdam';
  const shiftEnd = formatShiftEnd(data.shift_end_utc, tz);

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">On-Call Now</p>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary text-primary-foreground text-sm font-semibold">
          {initials(data.analyst.name)}
        </div>
        <div>
          <p className="text-sm font-medium text-foreground">{data.analyst.name}</p>
          <p className="text-xs text-muted-foreground">
            {data.shift_block?.label} · Until {shiftEnd} ({tz})
          </p>
        </div>
        <button
          onClick={onHandOffNow}
          disabled={!onHandOffNow}
          className="ml-auto rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Hand Off Now
        </button>
      </div>
    </div>
  );
}

export function OnCallWidgetCompact() {
  const { staffProfile } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/oncall/current/')
      .then(res => setData(res.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return null;

  if (!data?.analyst) {
    return (
      <div className="flex items-center gap-1.5 rounded-md bg-destructive/10 border border-destructive/30 px-3 py-1.5">
        <AlertTriangle className="h-3.5 w-3.5 text-destructive" />
        <span className="text-xs font-medium text-destructive">No on-call scheduled</span>
      </div>
    );
  }

  const tz = staffProfile?.timezone || 'Europe/Amsterdam';
  const shiftEnd = formatShiftEnd(data.shift_end_utc, tz);

  return (
    <div className="flex items-center gap-2 rounded-md bg-muted/50 border border-border px-3 py-1.5">
      <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground text-xs font-semibold">
        {initials(data.analyst.name)}
      </div>
      <span className="text-xs text-foreground font-medium">{data.analyst.name}</span>
      {shiftEnd && <span className="text-xs text-muted-foreground">until {shiftEnd}</span>}
    </div>
  );
}
