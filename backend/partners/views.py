from rest_framework import generics
from rest_framework.permissions import IsAdminUser

from .models import Connection
from .serializers import ConnectionSerializer


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
