import pytest
from django.utils import timezone

from blog.models import Post


@pytest.mark.django_db
def test_slug_auto_generated_from_title():
    post = Post.objects.create(title="Hello World", content="body", status=Post.STATUS_DRAFT)
    assert post.slug == "hello-world"


@pytest.mark.django_db
def test_slug_collision_resolved_with_counter():
    Post.objects.create(title="Hello World", content="body", status=Post.STATUS_DRAFT)
    post2 = Post.objects.create(title="Hello World", content="body 2", status=Post.STATUS_DRAFT)
    assert post2.slug == "hello-world-1"


@pytest.mark.django_db
def test_published_at_set_when_status_becomes_published():
    post = Post.objects.create(title="My Post", content="body", status=Post.STATUS_PUBLISHED)
    assert post.published_at is not None


@pytest.mark.django_db
def test_published_at_not_set_for_draft():
    post = Post.objects.create(title="My Post", content="body", status=Post.STATUS_DRAFT)
    assert post.published_at is None


@pytest.mark.django_db
def test_published_at_not_overwritten_on_resave():
    post = Post.objects.create(title="My Post", content="body", status=Post.STATUS_PUBLISHED)
    original_published_at = post.published_at
    post.content = "updated"
    post.save()
    assert post.published_at == original_published_at
