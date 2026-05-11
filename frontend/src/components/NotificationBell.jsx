import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import SlideOver from './SlideOver';

function BellIcon({ hasUnread }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      className="h-5 w-5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
      aria-hidden="true"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
      />
    </svg>
  );
}

function NotificationItem({ notification, onRead }) {
  const navigate = useNavigate();
  const isUnread = !notification.read_at;
  const title = notification.payload?.title ?? notification.kind;
  const body = notification.payload?.body ?? '';

  async function handleClick() {
    if (isUnread) {
      await api.post(`/api/me/notifications/${notification.id}/read/`).catch(() => {});
      onRead(notification.id);
    }
    if (notification.incident_id) {
      navigate(`/incidents/${notification.incident_id}`);
    }
  }

  return (
    <button
      onClick={handleClick}
      className={`w-full text-left px-6 py-4 border-b border-border hover:bg-accent transition-colors ${
        isUnread ? 'bg-accent/30' : ''
      }`}
    >
      <div className="flex items-start gap-2">
        {isUnread && (
          <span className="mt-1.5 h-2 w-2 flex-shrink-0 rounded-full bg-primary" aria-hidden="true" />
        )}
        <div className={isUnread ? '' : 'ml-4'}>
          <p className="text-sm font-medium text-foreground">{title}</p>
          {body && <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{body}</p>}
          <p className="text-xs text-muted-foreground mt-1">
            {new Date(notification.created_at).toLocaleString()}
          </p>
        </div>
      </div>
    </button>
  );
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await api.get('/api/me/notifications/unread-count/');
      setUnreadCount(res.data.unread_count);
    } catch {
      // silently ignore
    }
  }, []);

  useEffect(() => {
    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30_000);
    return () => clearInterval(interval);
  }, [fetchUnreadCount]);

  async function handleOpen() {
    setOpen(true);
    setLoading(true);
    try {
      const res = await api.get('/api/me/notifications/');
      setNotifications(res.data.results);
    } catch {
      setNotifications([]);
    } finally {
      setLoading(false);
    }
  }

  function handleNotificationRead(id) {
    setNotifications(prev =>
      prev.map(n => n.id === id ? { ...n, read_at: new Date().toISOString() } : n)
    );
    setUnreadCount(prev => Math.max(0, prev - 1));
  }

  async function handleMarkAllRead() {
    await api.post('/api/me/notifications/read-all/').catch(() => {});
    setNotifications(prev => prev.map(n => ({ ...n, read_at: n.read_at ?? new Date().toISOString() })));
    setUnreadCount(0);
  }

  return (
    <>
      <button
        onClick={handleOpen}
        aria-label={`Notifications${unreadCount > 0 ? `, ${unreadCount} unread` : ''}`}
        className="relative rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        data-testid="notification-bell"
      >
        <BellIcon hasUnread={unreadCount > 0} />
        {unreadCount > 0 && (
          <span
            data-testid="unread-badge"
            className="absolute -top-0.5 -right-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground"
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      <SlideOver
        open={open}
        onClose={() => setOpen(false)}
        title="Notifications"
        loading={loading}
      >
        <div className="flex items-center justify-between px-6 py-3 border-b border-border">
          <span className="text-xs text-muted-foreground">
            {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
          </span>
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="text-xs text-primary hover:underline"
            >
              Mark all read
            </button>
          )}
        </div>
        {notifications.length === 0 ? (
          <p className="px-6 py-8 text-sm text-muted-foreground">No notifications yet.</p>
        ) : (
          notifications.map(n => (
            <NotificationItem
              key={n.id}
              notification={n}
              onRead={handleNotificationRead}
            />
          ))
        )}
      </SlideOver>
    </>
  );
}
