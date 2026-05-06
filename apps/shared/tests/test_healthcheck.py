import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_healthcheck_returns_ok(client) -> None:
    response = client.get(reverse("shared:healthcheck"))

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_index_page_renders(client) -> None:
    response = client.get(reverse("shared:index"))

    assert response.status_code == 200
    assert "Учебная платформа" in response.content.decode()
    assert reverse("public_preview") in response.content.decode()
    assert reverse("accounts:login") in response.content.decode()
