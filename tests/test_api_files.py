import asyncio
from pathlib import Path
from fastapi.testclient import TestClient
from app.storage import Storage
from app.pipeline import PipelineManager, FakeBackend
from app.api import create_app

WEB_DIR = str(Path(__file__).resolve().parents[1] / "app" / "web")


def build(tmp_path):
    storage = Storage(str(tmp_path))
    mgr = PipelineManager(FakeBackend(), storage)
    asyncio.run(mgr.load())
    return TestClient(create_app(mgr, storage, WEB_DIR)), storage


def test_get_file_serves_glb(tmp_path):
    client, storage = build(tmp_path)
    jid = storage.new_job_id()
    storage.path_for(jid).write_bytes(b"GLBDATA")
    r = client.get(f"/files/{jid}.glb")
    assert r.status_code == 200
    assert r.headers["content-type"] == "model/gltf-binary"
    assert r.content == b"GLBDATA"


def test_get_file_404(tmp_path):
    client, storage = build(tmp_path)
    jid = storage.new_job_id()
    assert client.get(f"/files/{jid}.glb").status_code == 404


def test_get_file_invalid_id_400(tmp_path):
    client, _ = build(tmp_path)
    assert client.get("/files/not-a-valid-id.glb").status_code == 400


def test_delete_file(tmp_path):
    client, storage = build(tmp_path)
    jid = storage.new_job_id()
    storage.path_for(jid).write_bytes(b"X")
    assert client.delete(f"/files/{jid}.glb").status_code == 204
    assert storage.exists(jid) is False
    assert client.delete(f"/files/{jid}.glb").status_code == 404


def test_module_app_importable():
    import app.api as api
    assert hasattr(api, "app")
