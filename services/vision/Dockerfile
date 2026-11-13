FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# Install CPU wheels explicitly.  The default PyPI torch distribution pulls
# several gigabytes of CUDA runtimes, which is unnecessary for the portable
# local deployment and prevents it from running on hosts without NVIDIA.
RUN pip install --no-cache-dir \
    --no-deps \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.9.1+cpu torchvision==0.24.1+cpu \
    && sed -e '/^torch>=/d' -e '/^torchvision>=/d' requirements.txt > /tmp/requirements-no-torch.txt \
    && printf '%s\n' 'torch==2.9.1+cpu' 'torchvision==0.24.1+cpu' > /tmp/torch-constraints.txt \
    && pip install --no-cache-dir --index-url https://pypi.org/simple \
       --extra-index-url https://download.pytorch.org/whl/cpu \
       --constraint /tmp/torch-constraints.txt \
       -r /tmp/requirements-no-torch.txt

# Bundle the pinned default detector so a fresh or offline runtime does not
# depend on an implicit first-start download from Ultralytics.
ARG YOLO_WEIGHTS_URL=https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
ARG YOLO_WEIGHTS_SHA256=f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36
RUN curl -fsSL --retry 3 --retry-delay 2 "$YOLO_WEIGHTS_URL" -o /app/yolov8n.pt \
    && echo "$YOLO_WEIGHTS_SHA256  /app/yolov8n.pt" | sha256sum -c -

# shared models package (mounted at /shared in compose)
ENV PYTHONPATH="/shared:$PYTHONPATH"

COPY src/ ./src/
CMD ["python", "-m", "src.main"]
