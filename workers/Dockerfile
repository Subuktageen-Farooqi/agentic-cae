FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglu1-mesa libxrender1 libxext6 libsm6 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir cadquery==2.6.1 pydantic==2.14.1
WORKDIR /opt/cae
COPY schemas.py ./
COPY workers/__init__.py workers/cad_worker.py workers/container_entry.py ./workers/
ENV PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=2
USER 65532:65532
ENTRYPOINT ["python", "-m", "workers.container_entry"]
