import pytest
from pydantic import ValidationError
from app.schemas import GenerateParams, GenerateJsonRequest, GenerateResponse


def test_defaults():
    p = GenerateParams()
    assert p.seed == 0
    assert p.ss_steps == 12
    assert p.simplify == 0.95
    assert p.texture_size == 1024
    assert p.inline is False


def test_texture_size_must_be_allowed_value():
    with pytest.raises(ValidationError):
        GenerateParams(texture_size=999)


def test_simplify_range():
    with pytest.raises(ValidationError):
        GenerateParams(simplify=1.5)


def test_json_request_carries_image():
    r = GenerateJsonRequest(image_base64="abc", seed=5)
    assert r.image_base64 == "abc"
    assert r.seed == 5


def test_generate_response_shape():
    r = GenerateResponse(job_id="x", url="/files/x.glb", seed=1,
                         duration_ms=10, size_bytes=20)
    assert r.url == "/files/x.glb"
