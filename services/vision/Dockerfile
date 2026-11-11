FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxrender1 libxext6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
# Install CPU wheels explicitly.  The default PyPI torch distribution pulls
# several gigabytes of CUDA runtimes, which is unnecessary for the portable
# local deployment and prevents it from running on hosts without NVIDIA.
RUN pip install --no-cache-dir \
    --no-deps \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1+cpu torchvision==0.20.1+cpu \
    && sed -e '/^torch>=/d' -e '/^torchvision>=/d' requirements.txt > /tmp/requirements-no-torch.txt \
    && printf '%s\n' 'torch==2.5.1+cpu' 'torchvision==0.20.1+cpu' > /tmp/torch-constraints.txt \
    && pip install --no-cache-dir --index-url https://pypi.org/simple \
       --extra-index-url https://download.pytorch.org/whl/cpu \
       --constraint /tmp/torch-constraints.txt \
       -r /tmp/requirements-no-torch.txt

# shared models package (mounted at /shared in compose)
ENV PYTHONPATH="/shared:$PYTHONPATH"

COPY src/ ./src/
CMD ["python", "-m", "src.main"]
