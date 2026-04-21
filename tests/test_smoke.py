from django.test import Client


def test_health_endpoint_returns_ok() -> None:
    client = Client()

    response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "tsms"}


def test_home_page_renders() -> None:
    client = Client()

    response = client.get("/")

    assert response.status_code == 200
    assert b"Timesheet Management System" in response.content
