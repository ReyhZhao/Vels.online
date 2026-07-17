from django.shortcuts import get_object_or_404
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
    queryset = IntakeInboxMessage.objects.select_related("replayed_incident")

    def get_serializer_context(self):
        """Prebuild a {lowercased sender address → {id, name}} map of *active* Connections
        so each row can surface its covering Connection without an N+1 (ADR-0035)."""
        from .models import ConnectionSender

        context = super().get_serializer_context()
        sender_map = {}
        rows = (
            ConnectionSender.objects.filter(connection__active=True)
            .select_related("connection")
            .values_list("address", "connection_id", "connection__name")
        )
        for address, conn_id, conn_name in rows:
            sender_map[(address or "").strip().lower()] = {"id": conn_id, "name": conn_name}
        context["active_sender_map"] = sender_map
        return context


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


class ConnectionReplayIntakeView(APIView):
    """Replay a Connection's held Intake Inbox backlog through the live partner pipeline
    (ADR-0035). Staff-only.

    - GET previews the covered held rows, dry-running the field mapping to show each
      message's extracted External Reference (or that it has none), without mutating.
    - POST replays the whole covered backlog oldest-first and returns per-message outcomes.
    """

    permission_classes = [IsAdminUser]

    def _connection(self, pk):
        return get_object_or_404(Connection, pk=pk)

    def get(self, request, pk):
        from .replay import preview_connection_backlog

        connection = self._connection(pk)
        return Response(preview_connection_backlog(connection))

    def post(self, request, pk):
        from .replay import replay_connection_backlog

        connection = self._connection(pk)
        return Response({"results": replay_connection_backlog(connection)})
