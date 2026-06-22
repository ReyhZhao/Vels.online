from django.urls import path

from .views import AttackMapConfigView, AttackStreamView

urlpatterns = [
    path("stream/", AttackStreamView.as_view()),
    path("config/", AttackMapConfigView.as_view()),
]
