from rest_framework import generics
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Connection, IntakeInboxMessage
from .serializers import ConnectionSerializer, IntakeInboxMessageSerializer


class ConnectionListCreateView(generics.ListCreateAPIView):
    """Staff-only CRUD for partner Connections (ADR-0032). Non-staff receive 403."""

    permission_classes = [IsAdminUser]
    serializer_class = ConnectionSerializer

    def get_queryset(self):
        qs = (
            Connection.objects.all()
            .select_related("organization")
            .prefetch_related("senders")
        )
        if self.request.query_params.get("active") == "1":
            qs = qs.filter(active=True)
        return qs


class ConnectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ConnectionSerializer
    queryset = (
        Connection.objects.all().select_related("organization").prefetch_related("senders")
    )


class IntakeInboxListView(generics.ListAPIView):
    """Staff-only Intake Inbox: inbound mail that reached the SOC mailbox but no handler
    accepted (ADR-0032). Non-staff receive 403."""

    permission_classes = [IsAdminUser]
    serializer_class = IntakeInboxMessageSerializer
    queryset = IntakeInboxMessage.objects.all()


class IntakeInboxCountView(APIView):
    """Count of items in the Intake Inbox for the sidebar badge (#702). Staff-only."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({"count": IntakeInboxMessage.objects.count()})


class IntakeInboxDetailView(generics.RetrieveDestroyAPIView):
    """Staff can dismiss a handled Intake Inbox row."""

    permission_classes = [IsAdminUser]
    serializer_class = IntakeInboxMessageSerializer
    queryset = IntakeInboxMessage.objects.all()
