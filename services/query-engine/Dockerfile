FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
# Keep sentence-transformers on the portable CPU torch wheels instead of
# pulling the multi-gigabyte CUDA distribution from the default index.
RUN pip install --no-cache-dir \
    --no-deps \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.2.2+cpu torchvision==0.17.2+cpu \
    && printf '%s\n' 'torch==2.2.2+cpu' 'torchvision==0.17.2+cpu' > /tmp/torch-constraints.txt \
    && pip install --no-cache-dir --index-url https://pypi.org/simple \
       --extra-index-url https://download.pytorch.org/whl/cpu \
       --constraint /tmp/torch-constraints.txt \
       -r requirements.txt
ENV PYTHONPATH="/shared:$PYTHONPATH"
COPY src/ ./src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]
