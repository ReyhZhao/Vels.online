from django.urls import path

from .views import (
    NotificationDeleteView,
    NotificationListView,
    NotificationPreferencesView,
    NotificationReadAllView,
    NotificationReadView,
    UnreadCountView,
)

urlpatterns = [
    path("notification-prefs/", NotificationPreferencesView.as_view()),
    path("notifications/", NotificationListView.as_view()),
    path("notifications/unread-count/", UnreadCountView.as_view()),
    path("notifications/read-all/", NotificationReadAllView.as_view()),
    path("notifications/<int:pk>/read/", NotificationReadView.as_view()),
    path("notifications/<int:pk>/", NotificationDeleteView.as_view()),
]
