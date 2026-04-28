import pytest

from blog.models import Post


@pytest.fixture
def published_post():
    return Post.objects.create(
        title="Published Post",
        content="Published content",
        status=Post.STATUS_PUBLISHED,
    )


@pytest.fixture
def draft_post():
    return Post.objects.create(
        title="Draft Post",
        content="Draft content",
        status=Post.STATUS_DRAFT,
    )


@pytest.mark.django_db
def test_public_list_returns_only_published(client, published_post, draft_post):
    response = client.get("/api/posts/")
    assert response.status_code == 200
    slugs = [p["slug"] for p in response.json()]
    assert published_post.slug in slugs
    assert draft_post.slug not in slugs


@pytest.mark.django_db
def test_public_detail_returns_published_post(client, published_post):
    response = client.get(f"/api/posts/{published_post.slug}/")
    assert response.status_code == 200
    assert response.json()["title"] == "Published Post"


@pytest.mark.django_db
def test_public_detail_returns_404_for_draft(client, draft_post):
    response = client.get(f"/api/posts/{draft_post.slug}/")
    assert response.status_code == 404


# --- Write permission tests ---

@pytest.mark.django_db
def test_unauthenticated_create_returns_403(client):
    response = client.post(
        "/api/posts/",
        {"title": "New", "content": "body", "status": "draft"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_unauthenticated_update_returns_403(client, published_post):
    response = client.patch(
        f"/api/posts/{published_post.slug}/",
        {"title": "Hacked"},
        content_type="application/json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_unauthenticated_delete_returns_403(client, published_post):
    response = client.delete(f"/api/posts/{published_post.slug}/")
    assert response.status_code == 403


@pytest.mark.django_db
def test_admin_can_create_post(admin_client):
    response = admin_client.post(
        "/api/posts/",
        {"title": "Admin Post", "content": "body", "status": "draft"},
        content_type="application/json",
    )
    assert response.status_code == 201
    assert response.json()["slug"] == "admin-post"


@pytest.mark.django_db
def test_admin_can_update_post(admin_client, draft_post):
    response = admin_client.patch(
        f"/api/posts/{draft_post.slug}/",
        {"title": "Updated Title"},
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.django_db
def test_admin_can_delete_post(admin_client, draft_post):
    response = admin_client.delete(f"/api/posts/{draft_post.slug}/")
    assert response.status_code == 204
    assert not Post.objects.filter(slug=draft_post.slug).exists()


@pytest.mark.django_db
def test_admin_list_includes_drafts(admin_client, published_post, draft_post):
    response = admin_client.get("/api/posts/")
    assert response.status_code == 200
    slugs = [p["slug"] for p in response.json()]
    assert published_post.slug in slugs
    assert draft_post.slug in slugs
