"""
Tests for POST /api/feedback/issue/ (issue #115).
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def staff(db, django_user_model):
    return django_user_model.objects.create_user(username="staffy", password="p", is_staff=True)


@pytest.fixture
def member(db, django_user_model):
    return django_user_model.objects.create_user(username="member", password="p", is_staff=False)


VALID_PAYLOAD = {
    "type": "bug",
    "title": "Login button broken",
    "description": "Clicking login does nothing.",
    "path": "/dashboard",
}


def post_issue(client, payload=None, **kwargs):
    return client.post(
        "/api/feedback/issue/",
        payload or VALID_PAYLOAD,
        content_type="application/json",
        **kwargs,
    )


# ── auth / permission ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_unauthenticated_returns_403(client):
    r = post_issue(client)
    assert r.status_code == 403


@pytest.mark.django_db
def test_non_staff_returns_403(client, member):
    client.force_login(member)
    r = post_issue(client)
    assert r.status_code == 403


# ── unconfigured integration ──────────────────────────────────────────────────

@pytest.mark.django_db
def test_returns_503_when_token_missing(client, staff, settings):
    settings.GITHUB_TOKEN = ""
    settings.GITHUB_REPO = "owner/repo"
    client.force_login(staff)
    r = post_issue(client)
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"]


@pytest.mark.django_db
def test_returns_503_when_repo_missing(client, staff, settings):
    settings.GITHUB_TOKEN = "ghp_fake"
    settings.GITHUB_REPO = ""
    client.force_login(staff)
    r = post_issue(client)
    assert r.status_code == 503


# ── validation ────────────────────────────────────────────────────────────────

@pytest.mark.django_db
@pytest.mark.parametrize("missing_field", ["type", "title", "description", "path"])
def test_missing_field_returns_400(client, staff, settings, missing_field):
    settings.GITHUB_TOKEN = "ghp_fake"
    settings.GITHUB_REPO = "owner/repo"
    client.force_login(staff)
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != missing_field}
    r = client.post("/api/feedback/issue/", payload, content_type="application/json")
    assert r.status_code == 400
    assert missing_field in r.json()


@pytest.mark.django_db
def test_invalid_type_returns_400(client, staff, settings):
    settings.GITHUB_TOKEN = "ghp_fake"
    settings.GITHUB_REPO = "owner/repo"
    client.force_login(staff)
    r = post_issue(client, {**VALID_PAYLOAD, "type": "invalid"})
    assert r.status_code == 400
    assert "type" in r.json()


# ── success path ──────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_successful_bug_returns_201_with_issue_url(client, staff, settings):
    settings.GITHUB_TOKEN = "ghp_fake"
    settings.GITHUB_REPO = "owner/repo"
    client.force_login(staff)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"html_url": "https://github.com/owner/repo/issues/42"}
    mock_resp.raise_for_status = MagicMock()

    with patch("feedback.views.http_requests.post", return_value=mock_resp) as mock_post:
        r = post_issue(client)

    assert r.status_code == 201
    assert r.json()["issue_url"] == "https://github.com/owner/repo/issues/42"

    call_kwargs = mock_post.call_args
    body = call_kwargs.kwargs["json"]
    assert body["labels"] == ["bug"]
    assert "Login button broken" == body["title"]


@pytest.mark.django_db
def test_feature_type_uses_enhancement_label(client, staff, settings):
    settings.GITHUB_TOKEN = "ghp_fake"
    settings.GITHUB_REPO = "owner/repo"
    client.force_login(staff)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"html_url": "https://github.com/owner/repo/issues/43"}
    mock_resp.raise_for_status = MagicMock()

    with patch("feedback.views.http_requests.post", return_value=mock_resp) as mock_post:
        r = post_issue(client, {**VALID_PAYLOAD, "type": "feature"})

    assert r.status_code == 201
    body = mock_post.call_args.kwargs["json"]
    assert body["labels"] == ["enhancement"]


@pytest.mark.django_db
def test_issue_body_includes_description_path_and_reporter(client, staff, settings):
    settings.GITHUB_TOKEN = "ghp_fake"
    settings.GITHUB_REPO = "owner/repo"
    client.force_login(staff)

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"html_url": "https://github.com/owner/repo/issues/44"}
    mock_resp.raise_for_status = MagicMock()

    with patch("feedback.views.http_requests.post", return_value=mock_resp) as mock_post:
        post_issue(client)

    body_text = mock_post.call_args.kwargs["json"]["body"]
    assert "Clicking login does nothing." in body_text
    assert "/dashboard" in body_text
    assert "staffy" in body_text


# ── GitHub API failure ────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_github_api_failure_returns_502(client, staff, settings):
    settings.GITHUB_TOKEN = "ghp_fake"
    settings.GITHUB_REPO = "owner/repo"
    client.force_login(staff)

    with patch("feedback.views.http_requests.post", side_effect=Exception("network error")):
        r = post_issue(client)

    assert r.status_code == 502
    assert "Failed to create" in r.json()["detail"]
