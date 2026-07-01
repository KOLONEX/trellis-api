from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_TEXTURE_SIZES = {512, 1024, 2048}


class GenerateParams(BaseModel):
    seed: int = Field(default=0, ge=0)
    ss_steps: int = Field(default=12, ge=1, le=50)
    ss_cfg_strength: float = Field(default=7.5, ge=0.0, le=20.0)
    slat_steps: int = Field(default=12, ge=1, le=50)
    slat_cfg_strength: float = Field(default=3.0, ge=0.0, le=20.0)
    simplify: float = Field(default=0.95, ge=0.0, le=1.0)
    texture_size: int = Field(default=1024)
    inline: bool = False

    @field_validator("texture_size")
    @classmethod
    def _check_texture_size(cls, v: int) -> int:
        if v not in ALLOWED_TEXTURE_SIZES:
            raise ValueError(f"texture_size must be one of {sorted(ALLOWED_TEXTURE_SIZES)}")
        return v


class GenerateJsonRequest(GenerateParams):
    image_base64: str


class GenerateResponse(BaseModel):
    job_id: str
    url: str
    seed: int
    duration_ms: int
    size_bytes: int


class HealthResponse(BaseModel):
    # `model_loaded` collides with pydantic's protected `model_` namespace; allow it.
    model_config = ConfigDict(protected_namespaces=())

    status: str
    gpu: Optional[str] = None
    vram_free_mb: Optional[int] = None
    model_loaded: bool = False
    busy: bool = False
