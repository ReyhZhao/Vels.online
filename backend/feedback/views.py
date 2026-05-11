import logging

import requests as http_requests
from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


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
        except http_requests.exceptions.HTTPError as exc:
            gh_resp = exc.response
            code = gh_resp.status_code if gh_resp is not None else None
            logger.error(
                "GitHub API error %s creating issue: %s",
                code,
                gh_resp.text if gh_resp is not None else "(no response body)",
            )
            if code == 401:
                return Response(
                    {"detail": "GitHub token is invalid or missing required scope. Check the GITHUB_TOKEN setting."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            if code == 403:
                return Response(
                    {"detail": "GitHub token does not have permission to create issues. Check the GITHUB_TOKEN setting."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            if code == 404:
                return Response(
                    {"detail": "GitHub repository not found. Check the GITHUB_REPO setting."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(
                {"detail": "Failed to create GitHub issue."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception as exc:
            logger.error("Network error calling GitHub API: %s", exc)
            return Response(
                {"detail": "Failed to create GitHub issue."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"issue_url": resp.json()["html_url"]}, status=status.HTTP_201_CREATED)
