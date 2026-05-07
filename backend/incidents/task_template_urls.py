from django.urls import path

from .views import (
    TaskTemplateDetailView,
    TaskTemplateItemDetailView,
    TaskTemplateItemListView,
    TaskTemplateListView,
)

urlpatterns = [
    path("", TaskTemplateListView.as_view()),
    path("<int:pk>/", TaskTemplateDetailView.as_view()),
    path("<int:pk>/items/", TaskTemplateItemListView.as_view()),
    path("<int:pk>/items/<int:item_pk>/", TaskTemplateItemDetailView.as_view()),
]
