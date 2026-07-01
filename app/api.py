import base64
import binascii
import io
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, UnidentifiedImageError

from app.pipeline import PipelineManager
from app.schemas import (GenerateJsonRequest, GenerateParams,
                         GenerateResponse, HealthResponse)
from app.storage import Storage


def _gpu_stats():
    """Return (gpu_name, vram_free_mb) or (None, None) if torch/CUDA absent."""
    try:
        import torch
        if not torch.cuda.is_available():
            return None, None
        free, _ = torch.cuda.mem_get_info()
        return torch.cuda.get_device_name(0), int(free // (1024 * 1024))
    except Exception:
        return None, None


def create_app(manager: PipelineManager, storage: Storage,
               web_dir: str, max_upload_mb: int = 10, lifespan=None) -> FastAPI:
    app = FastAPI(title="TRELLIS Image-to-3D API", version="1.0", lifespan=lifespan)
    index_path = Path(web_dir) / "index.html"

    # Serve bundled frontend assets (three.js and addons) locally so the UI works
    # fully offline. Mounted under /vendor; the importmap in index.html points here.
    vendor_dir = Path(web_dir) / "vendor"
    if vendor_dir.is_dir():
        app.mount("/vendor", StaticFiles(directory=str(vendor_dir)), name="vendor")

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.get("/health", response_model=HealthResponse)
    async def health():
        gpu, vram = _gpu_stats()
        return HealthResponse(
            status="ok" if manager.model_loaded else "loading",
            gpu=gpu,
            vram_free_mb=vram,
            model_loaded=manager.model_loaded,
            busy=manager.busy,
        )

    def _decode_image(data: bytes) -> Image.Image:
        if len(data) > max_upload_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail="image too large")
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except (UnidentifiedImageError, OSError, ValueError):
            raise HTTPException(status_code=400, detail="invalid image")
        return img.convert("RGBA")

    async def _run_and_respond(image: Image.Image, params: GenerateParams):
        if not manager.model_loaded:
            raise HTTPException(status_code=503, detail="model not loaded")
        result = await manager.generate(image, params)
        if params.inline:
            return Response(
                content=result.glb_path.read_bytes(),
                media_type="model/gltf-binary",
                headers={
                    "X-Job-Id": result.job_id,
                    "X-Seed": str(result.seed),
                    "X-Duration-Ms": str(result.duration_ms),
                },
            )
        return JSONResponse(GenerateResponse(
            job_id=result.job_id,
            url=storage.url_for(result.job_id),
            seed=result.seed,
            duration_ms=result.duration_ms,
            size_bytes=result.size_bytes,
        ).model_dump())

    @app.post("/generate")
    async def generate(
        file: UploadFile = File(...),
        seed: int = Form(0),
        ss_steps: int = Form(12),
        ss_cfg_strength: float = Form(7.5),
        slat_steps: int = Form(12),
        slat_cfg_strength: float = Form(3.0),
        simplify: float = Form(0.95),
        texture_size: int = Form(1024),
        inline: bool = Form(False),
    ):
        data = await file.read()
        image = _decode_image(data)
        try:
            params = GenerateParams(
                seed=seed, ss_steps=ss_steps, ss_cfg_strength=ss_cfg_strength,
                slat_steps=slat_steps, slat_cfg_strength=slat_cfg_strength,
                simplify=simplify, texture_size=texture_size, inline=inline)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return await _run_and_respond(image, params)

    @app.post("/generate/json")
    async def generate_json(req: GenerateJsonRequest):
        try:
            data = base64.b64decode(req.image_base64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="invalid base64")
        image = _decode_image(data)
        params = GenerateParams(**req.model_dump(exclude={"image_base64"}))
        return await _run_and_respond(image, params)

    @app.get("/files/{job_id}.glb")
    async def get_file(job_id: str):
        if not storage.is_valid_job_id(job_id):
            raise HTTPException(status_code=400, detail="invalid job id")
        path = storage.path_for(job_id)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="not found")
        return Response(content=path.read_bytes(), media_type="model/gltf-binary")

    @app.delete("/files/{job_id}.glb", status_code=204)
    async def delete_file(job_id: str):
        if not storage.is_valid_job_id(job_id):
            raise HTTPException(status_code=400, detail="invalid job id")
        if not storage.delete(job_id):
            raise HTTPException(status_code=404, detail="not found")
        return Response(status_code=204)

    return app


import os

_OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/outputs")
_MODEL_PATH = os.environ.get("MODEL_PATH", "/opt/models/TRELLIS-image-large")
_MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "10"))
_WEB_DIR = str(Path(__file__).resolve().parent / "web")


def _build_default_app() -> FastAPI:
    from contextlib import asynccontextmanager

    from app.pipeline import TrellisBackend
    storage = Storage(_OUTPUT_DIR)
    manager = PipelineManager(TrellisBackend(_MODEL_PATH), storage)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await manager.load()
        yield

    return create_app(manager, storage, _WEB_DIR, _MAX_UPLOAD_MB, lifespan=lifespan)


app = _build_default_app()
