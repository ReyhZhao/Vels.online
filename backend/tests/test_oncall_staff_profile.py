import pytest
from django.contrib.auth.models import User

from oncall.models import StaffProfile


@pytest.mark.django_db
def test_staff_profile_auto_created_when_user_becomes_staff(django_user_model):
    user = django_user_model.objects.create_user(username="staffuser", password="pass", is_staff=False)
    assert not StaffProfile.objects.filter(user=user).exists()

    user.is_staff = True
    user.save()
    assert StaffProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_staff_profile_auto_created_on_create_with_staff(django_user_model):
    user = django_user_model.objects.create_user(username="staffuser2", password="pass", is_staff=True)
    assert StaffProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_get_profile_returns_403_for_non_staff(client, django_user_model):
    user = django_user_model.objects.create_user(username="regular", password="pass", is_staff=False)
    client.force_login(user)
    res = client.get("/api/oncall/me/profile/")
    assert res.status_code == 403


@pytest.mark.django_db
def test_get_profile_returns_timezone_for_staff(client, django_user_model):
    user = django_user_model.objects.create_user(username="staffu", password="pass", is_staff=True)
    client.force_login(user)
    res = client.get("/api/oncall/me/profile/")
    assert res.status_code == 200
    assert "timezone" in res.json()


@pytest.mark.django_db
def test_patch_profile_accepts_valid_timezone(client, django_user_model):
    user = django_user_model.objects.create_user(username="staffpatch", password="pass", is_staff=True)
    client.force_login(user)
    res = client.patch(
        "/api/oncall/me/profile/",
        data={"timezone": "America/New_York"},
        content_type="application/json",
    )
    assert res.status_code == 200
    assert res.json()["timezone"] == "America/New_York"


@pytest.mark.django_db
def test_patch_profile_rejects_invalid_timezone(client, django_user_model):
    user = django_user_model.objects.create_user(username="staffbad", password="pass", is_staff=True)
    client.force_login(user)
    res = client.patch(
        "/api/oncall/me/profile/",
        data={"timezone": "Imaginary/Timezone"},
        content_type="application/json",
    )
    assert res.status_code == 400
