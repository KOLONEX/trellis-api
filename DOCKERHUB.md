# TRELLIS API — Image → 3D `.glb`

HTTP API + three.js frontend that turns a **single 2D image into a 3D model** (`.glb`),
powered by [microsoft/TRELLIS](https://github.com/microsoft/TRELLIS).

The image is **self-contained and runs 100% offline** — the models
(TRELLIS-image-large + DINOv2 + rembg) and the frontend libraries (three.js) are baked in.
No internet, no downloads at runtime. Tested with `docker run --network none`.

---

## Quick start

```bash
docker run --gpus all -p 8000:8000 -v trellis-outputs:/outputs kolonex/trellis-api:latest
```

Open **http://localhost:8000** for the web frontend, or hit the API directly:

```bash
# returns JSON { url, ... }
curl -F file=@chair.png -F seed=42 http://localhost:8000/generate

# returns the GLB binary directly
curl -F file=@chair.png -F inline=true http://localhost:8000/generate -o out.glb
```

To use a different host port, remap it (container always listens on `8000`):

```bash
docker run --gpus all -p 5081:8000 -v /path/to/outputs:/outputs kolonex/trellis-api:latest
# → http://localhost:5081
```

---

## Requirements

- **NVIDIA GPU with ≥16 GB VRAM** and drivers compatible with **CUDA 11.8**.
- **[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)** (`--gpus all` is required).
- Built for `TORCH_CUDA_ARCH_LIST=8.6` (Ampere — e.g. RTX 3090 / 40xx). For other GPU
  architectures, rebuild from source with the matching arch.

**Verified on:** RTX 3090 (24 GB) — generation ~28 s, GLB ~2.5 MB with textures.

---

## API

| Method | Path | Description |
|---|---|---|
| `GET`    | `/`               | three.js frontend |
| `GET`    | `/health`         | model status and free VRAM |
| `POST`   | `/generate`       | multipart `file` + params → JSON `{url,...}` or GLB binary (`inline=true`) |
| `POST`   | `/generate/json`  | `{ image_base64, ... }` → same as above |
| `GET`    | `/files/{id}.glb` | download a generated model |
| `DELETE` | `/files/{id}.glb` | delete a generated model |

### Generation parameters
`seed` (0 = random), `ss_steps`, `ss_cfg_strength`, `slat_steps`, `slat_cfg_strength`,
`simplify` (0..1), `texture_size` (512 / 1024 / 2048), `inline` (bool).

---

## Configuration

Generated models are written to **`/outputs`** — mount a volume there to persist them.
The models themselves are baked into the image, so nothing else needs mounting.

| Env var | Default | Description |
|---|---|---|
| `OUTPUT_DIR`   | `/outputs`  | where generated `.glb` files are stored |
| `MAX_UPLOAD_MB`| `10`        | max input image size (MB) |
| `ATTN_BACKEND` | `xformers`  | attention backend (`xformers` or `flash-attn`) |
| `SPCONV_ALGO`  | `native`    | sparse-conv algorithm |

Example with a named container and a larger upload limit:

```bash
docker run --gpus all -p 5081:8000 \
  -v /path/to/outputs:/outputs \
  -e MAX_UPLOAD_MB=20 \
  --name trellis --restart unless-stopped \
  kolonex/trellis-api:latest
```

---

## Frontend

Vanilla HTML/JS, no build step, no external dependencies:

- **Local three.js viewer** — rotate (drag), zoom (wheel), pan (right-click drag).
- **Bilingual ES / EN** with a header switcher (remembers your choice, detects browser language).
- **Help icons** (`?`) on every parameter explaining what it does.

---

## Troubleshooting

- **OOM / HTTP 500 on generate:** the GPU has <16 GB free. Check `GET /health` → `vram_free_mb`.
- **No GPU detected:** ensure the NVIDIA Container Toolkit is installed and you pass `--gpus all`.
- **Want flash-attn instead of xformers:** set `ATTN_BACKEND=flash-attn` (slower to build, heavier on RAM).

---

*Based on [microsoft/TRELLIS](https://github.com/microsoft/TRELLIS). Model weights are subject to their respective licenses.*
