from django.urls import path

from .views import (
    ApplyTemplateView,
    IncidentCommentListView,
    IncidentDelegateView,
    IncidentDelegationReturnView,
    IncidentDetailView,
    IncidentListView,
    IncidentTaskListView,
    IncidentTimelineView,
    IncidentTransferView,
    IncidentTransitionView,
    PromoteView,
    StaffUserListView,
)

urlpatterns = [
    path("", IncidentListView.as_view()),
    path("promote/", PromoteView.as_view()),
    path("staff-users/", StaffUserListView.as_view()),
    path("<int:pk>/", IncidentDetailView.as_view()),
    path("<int:pk>/timeline/", IncidentTimelineView.as_view()),
    path("<int:pk>/transition/", IncidentTransitionView.as_view()),
    path("<int:pk>/transfer/", IncidentTransferView.as_view()),
    path("<int:pk>/delegate/", IncidentDelegateView.as_view()),
    path("<int:pk>/delegations/<int:delegation_id>/return/", IncidentDelegationReturnView.as_view()),
    path("<int:pk>/tasks/", IncidentTaskListView.as_view()),
    path("<int:pk>/apply-template/", ApplyTemplateView.as_view()),
    path("<int:pk>/comments/", IncidentCommentListView.as_view()),
]
