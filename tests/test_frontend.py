import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from app.storage import Storage
from app.pipeline import PipelineManager, FakeBackend
from app.api import create_app

WEB_DIR = str(Path(__file__).resolve().parents[1] / "app" / "web")


def test_index_has_viewer_machinery(tmp_path):
    storage = Storage(str(tmp_path))
    mgr = PipelineManager(FakeBackend(), storage)
    asyncio.run(mgr.load())
    client = TestClient(create_app(mgr, storage, WEB_DIR))
    html = client.get("/").text
    # importmap + three (served locally, not from a CDN) + controls/loaders
    assert "importmap" in html
    assert "/vendor/three/three.module.js" in html
    assert "https://unpkg.com" not in html  # fully local / offline
    assert "OrbitControls" in html
    assert "GLTFLoader" in html
    # it posts to /generate and consumes the json url
    assert "/generate" in html
    assert "id=\"generate\"" in html
    assert "id=\"canvas\"" in html
    # parameter help icons with explanations (Spanish defaults in markup)
    assert html.count("class=\"help\"") == 3
    assert "Semilla del generador" in html
    assert "Simplificación de la malla" in html
    assert "Resolución del mapa de textura" in html
    # ES/EN language toggle + English strings present in the i18n dictionary
    assert 'data-lang="es"' in html
    assert 'data-lang="en"' in html
    assert "Generation seed" in html
    assert "Generate" in html


def test_vendor_assets_served_locally(tmp_path):
    storage = Storage(str(tmp_path))
    mgr = PipelineManager(FakeBackend(), storage)
    asyncio.run(mgr.load())
    client = TestClient(create_app(mgr, storage, WEB_DIR))
    for path in (
        "/vendor/three/three.module.js",
        "/vendor/three/addons/controls/OrbitControls.js",
        "/vendor/three/addons/loaders/GLTFLoader.js",
        "/vendor/three/addons/environments/RoomEnvironment.js",
        "/vendor/three/addons/utils/BufferGeometryUtils.js",
    ):
        r = client.get(path)
        assert r.status_code == 200, path
        assert len(r.content) > 0

