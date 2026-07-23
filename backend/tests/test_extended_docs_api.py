"""The in-depth handbook is served only to authenticated users.

The whole point of moving this content behind an API (rather than bundling it in
the public frontend) is that a logged-out visitor never receives it. These tests
pin that boundary.
"""

import pytest


@pytest.fixture
def user(db, django_user_model):
    return django_user_model.objects.create_user(username="alice", password="pass")


@pytest.mark.django_db
def test_extended_docs_requires_authentication(client):
    response = client.get("/api/docs/extended/")
    assert response.status_code == 401


@pytest.mark.django_db
def test_extended_docs_returns_sections_for_any_logged_in_user(client, user):
    client.force_login(user)
    response = client.get("/api/docs/extended/")

    assert response.status_code == 200
    sections = response.json()["sections"]
    assert len(sections) >= 1
    # Shape the frontend renders: section → articles → markdown body[].
    first = sections[0]
    assert {"id", "icon", "title", "summary", "articles"} <= set(first)
    assert first["articles"][0]["body"]
    # The Scheduled Search Rules material is present.
    ids = {s["id"] for s in sections}
    assert "ssr-core" in ids
