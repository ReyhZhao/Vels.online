import pytest


@pytest.mark.django_db
def test_login_redirect_sends_authenticated_staff_to_dashboard(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="staffuser", password="pass", is_staff=True
    )
    client.force_login(user)
    response = client.get("/login-redirect/")
    assert response.status_code == 302
    assert response["Location"] == "/dashboard"


@pytest.mark.django_db
def test_login_redirect_sends_authenticated_regular_user_to_dashboard(client, django_user_model):
    user = django_user_model.objects.create_user(
        username="regularuser", password="pass", is_staff=False
    )
    client.force_login(user)
    response = client.get("/login-redirect/")
    assert response.status_code == 302
    assert response["Location"] == "/dashboard"


@pytest.mark.django_db
def test_login_redirect_sends_unauthenticated_user_to_root(client):
    response = client.get("/login-redirect/")
    assert response.status_code == 302
    assert response["Location"] == "/"


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
    assert response["X-CSRFToken"], "X-CSRFToken header must be returned so SPA can set it as axios default"


@pytest.mark.django_db
def test_me_returns_401_for_anonymous(client):
    response = client.get("/api/me/")
    assert response.status_code == 401
    assert response["X-CSRFToken"], "X-CSRFToken header must be returned even for 401 so SPA can bootstrap CSRF"
