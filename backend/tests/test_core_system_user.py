import pytest
from django.contrib.auth.models import User


@pytest.mark.django_db
def test_get_system_user_returns_system_user():
    from core import get_system_user
    user = get_system_user()
    assert user.username == "system"


@pytest.mark.django_db
def test_system_user_is_inactive():
    from core import get_system_user
    user = get_system_user()
    assert user.is_active is False


@pytest.mark.django_db
def test_system_user_has_unusable_password():
    from core import get_system_user
    user = get_system_user()
    assert not user.has_usable_password()


@pytest.mark.django_db
def test_get_system_user_is_cached():
    from core.utils import get_system_user as _get
    _get.cache_clear()
    u1 = _get()
    u2 = _get()
    assert u1 is u2


@pytest.mark.django_db
def test_migration_is_idempotent():
    from django.contrib.auth.models import User
    from core import get_system_user
    # Running get_or_create again should not duplicate the user
    count_before = User.objects.filter(username="system").count()
    User.objects.get_or_create(username="system", defaults={"email": "system@vels.online", "is_active": False})
    assert User.objects.filter(username="system").count() == count_before
