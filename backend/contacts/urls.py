from django.urls import path
from .views import ContactDetailView, ContactListView

urlpatterns = [
    path("", ContactListView.as_view()),
    path("<int:pk>/", ContactDetailView.as_view()),
]
