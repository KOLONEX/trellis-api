FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    TORCH_CUDA_ARCH_LIST="8.6" \
    HF_HOME=/opt/models \
    ATTN_BACKEND=xformers \
    SPCONV_ALGO=native \
    OUTPUT_DIR=/outputs \
    MODEL_PATH=/opt/models/TRELLIS-image-large \
    MAX_UPLOAD_MB=10

# 1. System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
        git wget build-essential ninja-build \
        python3.10 python3.10-dev python3-pip \
        libgl1 libglib2.0-0 && \
    ln -sf /usr/bin/python3.10 /usr/bin/python && \
    rm -rf /var/lib/apt/lists/*

# 2. Torch (cu118) first, so extension builds find it
RUN pip install --no-cache-dir torch==2.4.0 torchvision==0.19.0 \
        --index-url https://download.pytorch.org/whl/cu118

# 3. Clone TRELLIS and compile extensions.
#    Two Docker-specific gotchas handled here:
#    (a) Run under bash, NOT `. ./setup.sh`: Docker RUN uses /bin/sh (dash), which does
#        not pass arguments to a sourced script -> setup.sh would see no args and only
#        print usage. setup.sh has no sourcing dependency (we don't use --new-env/conda).
#    (b) setup.sh gates all GPU-extension installs on `torch.cuda.is_available()`, which
#        is False during `docker build` (no GPU) -> every extension is silently skipped.
#        torch.version.cuda is truthy and nvcc is present, so we rewrite the detection to
#        compile the extensions at build time for TORCH_CUDA_ARCH_LIST without a GPU.
#    We use the xformers attention backend (prebuilt wheel) instead of flash-attn, whose
#    CUDA path builds from source here (very slow / memory-hungry). plyfile and a path-based
#    utils3d are needed by the gaussian/postprocessing code but are not installed correctly
#    by setup.sh --basic, so we handle them explicitly (see below).
WORKDIR /opt
RUN git clone --recurse-submodules https://github.com/microsoft/TRELLIS.git
WORKDIR /opt/TRELLIS
RUN sed -i 's/torch.cuda.is_available()/(torch.version.cuda is not None)/g' setup.sh
# Basic deps + the source-compiled / simple-wheel extensions that setup.sh handles right.
RUN bash ./setup.sh --basic --spconv --diffoctreerast --mipgaussian
# Extensions setup.sh mishandles for a pip-installed torch 2.4.0+cu118 (the README assumes
# a conda torch whose __version__ has no +cu118 suffix). Install them explicitly:
#  - xformers: setup.sh's `case 2.4.0)` never matches because PYTORCH_VERSION is
#    "2.4.0+cu118"; the correct command for this combo is the cu118 wheel below.
#  - kaolin: setup.sh points torch 2.4.0 at cu121 wheels (incompatible with cu118 torch);
#    NVIDIA does publish cu118 kaolin wheels for torch 2.4.0, used here.
#  - nvdiffrast: its setup.py imports torch at build time, so it needs --no-build-isolation.
RUN pip install --no-cache-dir --retries 6 --timeout 180 xformers==0.0.27.post2 --index-url https://download.pytorch.org/whl/cu118
RUN pip install --no-cache-dir --retries 6 --timeout 180 kaolin -f https://nvidia-kaolin.s3.us-east-2.amazonaws.com/torch-2.4.0_cu118.html
# The base image ships setuptools 59.6.0, too old to parse some packages' pyproject.toml
# [project].name -> they build as "UNKNOWN-0.0.0" and aren't importable. Upgrade first.
RUN pip install --no-cache-dir -U "setuptools>=70" wheel
# nvdiffrast: not on PyPI; setup.py imports torch so it needs --no-build-isolation, and
# it only builds with the upgraded setuptools above (else it installs as UNKNOWN).
RUN git clone --depth 1 https://github.com/NVlabs/nvdiffrast.git /tmp/nvdiffrast && \
        pip install --no-cache-dir --no-build-isolation /tmp/nvdiffrast
# plyfile is required by the gaussian representation but NOT installed by setup.sh --basic.
RUN pip install --no-cache-dir --retries 6 --timeout 180 plyfile
# utils3d (used by postprocessing_utils.to_glb, render_utils, gaussian_model): it is a
# pure-Python package, but its pyproject [project] table builds as UNKNOWN under pip here
# and is not importable. Put it on the path like trellis instead, and install its runtime dep.
RUN git clone https://github.com/EasternJournalist/utils3d.git /opt/utils3d && \
        cd /opt/utils3d && git checkout 9a4eb15e4021b67b12c460c7057d642626897ec8
RUN pip install --no-cache-dir --retries 6 --timeout 180 moderngl
# Guard: fail the build immediately if any dep/extension is missing (catches the dash
# no-op, the PLATFORM=cpu skip, and the version-case mismatches). GPU-free: find_spec
# locates modules without importing/initialising CUDA.
RUN python -c "import importlib.util as u, easydict, rembg, trimesh, transformers, onnxruntime, xatlas; \
        mods=['xformers','kaolin','spconv','nvdiffrast','diffoctreerast','diff_gaussian_rasterization','plyfile']; \
        miss=[m for m in mods if u.find_spec(m) is None]; \
        assert not miss, 'missing extensions: '+str(miss); print('trellis deps + extensions OK')"

# 4. API deps
COPY requirements-api.txt /tmp/requirements-api.txt
RUN pip install --no-cache-dir -r /tmp/requirements-api.txt

# 5. Bake the model into the image
COPY scripts/download_model.py /opt/scripts/download_model.py
RUN python /opt/scripts/download_model.py

# 6. App code. PYTHONPATH carries the repo-local packages that are not pip-installed:
#    /opt/TRELLIS (the `trellis` package) and /opt/utils3d. /app is for our `app.api:app`.
#    WORKDIR /app also matters: TRELLIS ships /opt/TRELLIS/app.py (its gradio demo), which
#    would shadow our `app` package if the CWD were /opt/TRELLIS — keeping CWD at /app wins.
WORKDIR /app
COPY app/ /app/app/
ENV PYTHONPATH=/app:/opt/TRELLIS:/opt/utils3d

# Final guard (GPU-free): runs after all pip installs with the final PYTHONPATH.
# Catches trellis/utils3d not importable and a transformers<->huggingface_hub clobber,
# all of which otherwise only surface at runtime.
RUN python -c "import importlib.util as u, transformers, utils3d; \
        assert u.find_spec('trellis'), 'trellis not on PYTHONPATH'; \
        print('guard: trellis + utils3d + transformers import OK')"

# 7. Bake the DINOv2 image encoder (~1.1GB) and the rembg background-removal model into the
#    caches so the first generation needs no internet and the model loads fast. CPU-only.
RUN python -c "import torch; torch.hub.load('facebookresearch/dinov2','dinov2_vitl14_reg',pretrained=True); print('dinov2 baked')"
RUN python -c "import rembg; rembg.new_session('u2net'); print('u2net baked')" || echo "rembg prebake skipped"

RUN mkdir -p /outputs
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
