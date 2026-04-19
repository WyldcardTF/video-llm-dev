FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DOTENV_PATH=/app/.env \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# System packages for Python builds + video handling
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    build-essential \
    curl \
    ffmpeg \
    git \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment inside the container
RUN python -m venv "$VIRTUAL_ENV"

# Install Python deps first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r /app/requirements.txt

# Copy project files. Runtime secrets are injected with docker-compose env_file
# and local bind mounts rather than baked into the image.
COPY . /app

CMD ["bash"]
