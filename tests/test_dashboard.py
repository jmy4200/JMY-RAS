from fastapi.testclient import TestClient

from backend.main import app


def test_dashboard_page_serves_html():
    with TestClient(app) as client:
        response = client.get("/dashboard/")
    assert response.status_code == 200
    assert "JMY-RAS" in response.text
    assert "Control Center" in response.text


def test_dashboard_assets_are_served():
    with TestClient(app) as client:
        css = client.get("/dashboard/assets/style.css")
        js = client.get("/dashboard/assets/app.js")
    assert css.status_code == 200
    assert "--bg" in css.text
    assert js.status_code == 200
    assert "api/system/info" in js.text
