import pytest


@pytest.mark.django_db
def test_me_returns_user_data_for_authenticated_session(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass123",
    )
    client.force_login(user)
    response = client.get("/api/me/")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user.id
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"


@pytest.mark.django_db
def test_me_returns_401_for_anonymous(client):
    response = client.get("/api/me/")
    assert response.status_code == 401
