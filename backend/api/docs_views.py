from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .docs_content import EXTENDED_DOC_SECTIONS


class ExtendedDocsView(APIView):
    """The in-depth handbook, returned only to authenticated users.

    This content is deliberately not in the public frontend bundle — gating it
    at the API means logged-out visitors never receive it at all.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"sections": EXTENDED_DOC_SECTIONS})
