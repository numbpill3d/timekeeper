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
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1+cpu torchvision==0.20.1+cpu \
    && pip install --no-cache-dir -r requirements.txt

# shared models package (mounted at /shared in compose)
ENV PYTHONPATH="/shared:$PYTHONPATH"

COPY src/ ./src/
CMD ["python", "-m", "src.main"]
