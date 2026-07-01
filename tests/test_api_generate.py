import asyncio
import base64
import io
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from app.storage import Storage
from app.pipeline import PipelineManager, FakeBackend
from app.api import create_app

WEB_DIR = str(Path(__file__).resolve().parents[1] / "app" / "web")


def make_png_bytes(size=(32, 32), color=(120, 80, 200)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def build_client(tmp_path, loaded=True, max_upload_mb=10):
    storage = Storage(str(tmp_path))
    mgr = PipelineManager(FakeBackend(), storage)
    if loaded:
        asyncio.run(mgr.load())
    return TestClient(create_app(mgr, storage, WEB_DIR, max_upload_mb)), storage


def test_generate_returns_json_with_url(tmp_path):
    client, storage = build_client(tmp_path)
    r = client.post("/generate",
                    files={"file": ("a.png", make_png_bytes(), "image/png")},
                    data={"seed": "42"})
    assert r.status_code == 200
    body = r.json()
    assert body["seed"] == 42
    assert body["url"] == f"/files/{body['job_id']}.glb"
    assert body["size_bytes"] == len(FakeBackend.GLB)
    assert storage.exists(body["job_id"])


def test_generate_inline_returns_binary(tmp_path):
    client, _ = build_client(tmp_path)
    r = client.post("/generate",
                    files={"file": ("a.png", make_png_bytes(), "image/png")},
                    data={"inline": "true", "seed": "9"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "model/gltf-binary"
    assert r.headers["x-seed"] == "9"
    assert "x-job-id" in r.headers
    assert r.content == FakeBackend.GLB


def test_generate_invalid_image_400(tmp_path):
    client, _ = build_client(tmp_path)
    r = client.post("/generate",
                    files={"file": ("a.png", b"not-an-image", "image/png")})
    assert r.status_code == 400


def test_generate_too_large_413(tmp_path):
    client, _ = build_client(tmp_path, max_upload_mb=1)
    big = b"\x89PNG\r\n" + b"0" * (2 * 1024 * 1024)
    r = client.post("/generate",
                    files={"file": ("a.png", big, "image/png")})
    assert r.status_code == 413


def test_generate_503_when_not_loaded(tmp_path):
    client, _ = build_client(tmp_path, loaded=False)
    r = client.post("/generate",
                    files={"file": ("a.png", make_png_bytes(), "image/png")})
    assert r.status_code == 503


def test_generate_json_base64(tmp_path):
    client, storage = build_client(tmp_path)
    b64 = base64.b64encode(make_png_bytes()).decode()
    r = client.post("/generate/json", json={"image_base64": b64, "seed": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["seed"] == 3
    assert storage.exists(body["job_id"])


def test_generate_json_invalid_base64_400(tmp_path):
    client, _ = build_client(tmp_path)
    r = client.post("/generate/json", json={"image_base64": "!!!notbase64!!!"})
    assert r.status_code == 400
