import asyncio
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.schemas import GenerateParams
from app.storage import Storage


class Backend(Protocol):
    def load(self) -> None: ...
    def run(self, image, params: GenerateParams, seed: int) -> bytes: ...


@dataclass
class GenerationResult:
    job_id: str
    glb_path: Path
    seed: int
    duration_ms: int
    size_bytes: int


class PipelineManager:
    def __init__(self, backend: Backend, storage: Storage):
        self._backend = backend
        self._storage = storage
        self._lock = asyncio.Lock()
        self._busy = False
        self._loaded = False

    async def load(self) -> None:
        await asyncio.to_thread(self._backend.load)
        self._loaded = True

    @property
    def model_loaded(self) -> bool:
        return self._loaded

    @property
    def busy(self) -> bool:
        return self._busy

    async def generate(self, image, params: GenerateParams) -> GenerationResult:
        async with self._lock:
            self._busy = True
            try:
                start = time.monotonic()
                seed = params.seed or random.randint(1, 2_147_483_647)
                glb_bytes = await asyncio.to_thread(self._backend.run, image, params, seed)
                job_id = self._storage.new_job_id()
                path = self._storage.path_for(job_id)
                path.write_bytes(glb_bytes)
                duration_ms = int((time.monotonic() - start) * 1000)
                return GenerationResult(
                    job_id=job_id, glb_path=path, seed=seed,
                    duration_ms=duration_ms, size_bytes=len(glb_bytes),
                )
            finally:
                self._busy = False


class FakeBackend:
    """In-memory backend for host tests (no GPU/torch)."""
    GLB = b"glTF-fake-bytes"

    def __init__(self):
        self.loaded = False
        self.last_seed = None
        self._in_flight = 0
        self.max_in_flight = 0

    def load(self) -> None:
        self.loaded = True

    def run(self, image, params: GenerateParams, seed: int) -> bytes:
        self._in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            time.sleep(0.01)
            self.last_seed = seed
            return self.GLB
        finally:
            self._in_flight -= 1


class TrellisBackend:
    """Real TRELLIS image-to-3D backend. Requires GPU + compiled extensions.
    All trellis/torch imports are lazy so this module imports on a plain host."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._pipe = None

    def load(self) -> None:
        from trellis.pipelines import TrellisImageTo3DPipeline
        self._pipe = TrellisImageTo3DPipeline.from_pretrained(self.model_path)
        self._pipe.cuda()

    def run(self, image, params: GenerateParams, seed: int) -> bytes:
        from trellis.utils import postprocessing_utils
        outputs = self._pipe.run(
            image,
            seed=seed,
            sparse_structure_sampler_params={
                "steps": params.ss_steps,
                "cfg_strength": params.ss_cfg_strength,
            },
            slat_sampler_params={
                "steps": params.slat_steps,
                "cfg_strength": params.slat_cfg_strength,
            },
        )
        glb = postprocessing_utils.to_glb(
            outputs["gaussian"][0],
            outputs["mesh"][0],
            simplify=params.simplify,
            texture_size=params.texture_size,
        )
        # trimesh export to bytes (no temp file needed)
        return glb.export(file_type="glb")
