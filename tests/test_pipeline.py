import asyncio
from app.storage import Storage
from app.schemas import GenerateParams
from app.pipeline import PipelineManager, FakeBackend


def test_generate_writes_glb_and_returns_result(tmp_path):
    storage = Storage(str(tmp_path))
    mgr = PipelineManager(FakeBackend(), storage)
    asyncio.run(mgr.load())
    assert mgr.model_loaded is True

    params = GenerateParams(seed=7)
    result = asyncio.run(mgr.generate("IMAGE", params))

    assert result.seed == 7
    assert result.size_bytes == len(FakeBackend.GLB)
    assert result.glb_path.read_bytes() == FakeBackend.GLB
    assert storage.is_valid_job_id(result.job_id)
    assert result.duration_ms >= 0


def test_seed_zero_becomes_random_nonzero(tmp_path):
    storage = Storage(str(tmp_path))
    backend = FakeBackend()
    mgr = PipelineManager(backend, storage)
    asyncio.run(mgr.load())

    result = asyncio.run(mgr.generate("IMAGE", GenerateParams(seed=0)))
    assert result.seed != 0
    assert backend.last_seed == result.seed


def test_mutex_serializes_concurrent_generations(tmp_path):
    storage = Storage(str(tmp_path))
    backend = FakeBackend()
    mgr = PipelineManager(backend, storage)
    asyncio.run(mgr.load())

    async def drive():
        r1, r2 = await asyncio.gather(
            mgr.generate("A", GenerateParams(seed=1)),
            mgr.generate("B", GenerateParams(seed=2)),
        )
        return r1, r2

    r1, r2 = asyncio.run(drive())
    # never ran concurrently: backend records max in-flight == 1
    assert backend.max_in_flight == 1
    assert {r1.seed, r2.seed} == {1, 2}


def test_trellis_backend_has_backend_interface():
    from app.pipeline import TrellisBackend
    assert hasattr(TrellisBackend, "load")
    assert hasattr(TrellisBackend, "run")
    # constructing must not import torch/trellis (lazy imports)
    backend = TrellisBackend("/opt/models/TRELLIS-image-large")
    assert backend.model_path == "/opt/models/TRELLIS-image-large"
    import sys
    assert "torch" not in sys.modules
