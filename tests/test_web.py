def test_ui_served_as_html(client):
    response = client.get("/ui")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "<html" in response.text.lower()


def test_ui_assets_served(client):
    expected = {
        "/ui/app.js": "text/javascript",
        "/ui/data.js": "text/javascript",
        "/ui/styles.css": "text/css",
    }
    for path, media_type in expected.items():
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["content-type"].startswith(media_type), path
        assert response.text.strip()


def test_ui_unknown_file_is_json_404(client):
    response = client.get("/ui/no-such-file.js")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["code"] == "not_found"
    assert "message" in body


def test_ui_does_not_shadow_api_paths(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    unknown = client.get("/no-such-route")
    assert unknown.status_code == 404
    assert unknown.headers["content-type"].startswith("application/json")


def test_ui_never_reaches_the_model(client, fake_llm):
    client.get("/ui")
    client.get("/ui/app.js")
    assert fake_llm.calls == []
