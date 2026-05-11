import requests as http_requests
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class CreateGithubIssueView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response(status=status.HTTP_403_FORBIDDEN)

        token = getattr(settings, "GITHUB_TOKEN", "")
        repo = getattr(settings, "GITHUB_REPO", "")
        if not token or not repo:
            return Response(
                {"detail": "GitHub integration is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        issue_type = request.data.get("type", "").strip()
        title = request.data.get("title", "").strip()
        description = request.data.get("description", "").strip()
        path = request.data.get("path", "").strip()

        errors = {}
        if issue_type not in ("bug", "feature"):
            errors["type"] = "Must be 'bug' or 'feature'."
        if not title:
            errors["title"] = "This field is required."
        if not description:
            errors["description"] = "This field is required."
        if not path:
            errors["path"] = "This field is required."
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        label = "bug" if issue_type == "bug" else "enhancement"
        body = (
            f"{description}\n\n"
            f"---\n"
            f"**Reported from:** `{path}`\n"
            f"**Reporter:** {request.user.username}"
        )

        try:
            resp = http_requests.post(
                f"https://api.github.com/repos/{repo}/issues",
                json={"title": title, "body": body, "labels": [label]},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=10,
            )
            resp.raise_for_status()
        except Exception:
            return Response(
                {"detail": "Failed to create GitHub issue."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"issue_url": resp.json()["html_url"]}, status=status.HTTP_201_CREATED)
