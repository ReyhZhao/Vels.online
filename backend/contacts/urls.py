from django.urls import path
from .views import ContactAssetDetailView, ContactAssetListView, ContactDetailView, ContactListView

urlpatterns = [
    path("", ContactListView.as_view()),
    path("<int:pk>/", ContactDetailView.as_view()),
    path("<int:contact_pk>/assets/", ContactAssetListView.as_view()),
    path("<int:contact_pk>/assets/<int:asset_pk>/", ContactAssetDetailView.as_view()),
]
