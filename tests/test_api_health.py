import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from app.storage import Storage
from app.pipeline import PipelineManager, FakeBackend
from app.api import create_app

WEB_DIR = str(Path(__file__).resolve().parents[1] / "app" / "web")


def build_client(tmp_path, loaded=True):
    storage = Storage(str(tmp_path))
    mgr = PipelineManager(FakeBackend(), storage)
    if loaded:
        asyncio.run(mgr.load())
    app = create_app(mgr, storage, WEB_DIR)
    return TestClient(app), mgr


def test_root_serves_html(tmp_path):
    client, _ = build_client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "canvas" in r.text


def test_health_reports_loaded(tmp_path):
    client, _ = build_client(tmp_path, loaded=True)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["model_loaded"] is True
    assert body["busy"] is False
    assert body["status"] == "ok"


def test_health_reports_not_loaded(tmp_path):
    client, _ = build_client(tmp_path, loaded=False)
    body = client.get("/health").json()
    assert body["model_loaded"] is False
    assert body["status"] == "loading"
