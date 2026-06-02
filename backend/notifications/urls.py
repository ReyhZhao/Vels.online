from django.urls import path

from .views import (
    EmailTemplateDetailView,
    EmailTemplateListView,
    NotificationDeleteView,
    NotificationListView,
    NotificationPreferencesView,
    NotificationReadAllView,
    NotificationReadView,
    PushSubscribeView,
    PushVapidKeyView,
    TestPushView,
    UnreadCountView,
)

urlpatterns = [
    path("notification-prefs/", NotificationPreferencesView.as_view()),
    path("notifications/", NotificationListView.as_view()),
    path("notifications/unread-count/", UnreadCountView.as_view()),
    path("notifications/read-all/", NotificationReadAllView.as_view()),
    path("notifications/<int:pk>/read/", NotificationReadView.as_view()),
    path("notifications/<int:pk>/", NotificationDeleteView.as_view()),
    path("email-templates/", EmailTemplateListView.as_view()),
    path("email-templates/<str:name>/", EmailTemplateDetailView.as_view()),
    path("push/vapid-public-key/", PushVapidKeyView.as_view()),
    path("push/subscribe/", PushSubscribeView.as_view()),
    path("push/test/", TestPushView.as_view()),
]
