# Base image with CUDA 12.9.0 support
FROM nvidia/cuda:12.9.0-devel-ubuntu22.04

# Set non-interactive frontend for package installers
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3.10 \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Set environment variables
ENV FLASH_ATTENTION_2=1
ENV VLLM_FLASH_ATTN_VERSION=2

# --- STAGE 1: Build the stable, unchanging core dependencies ---
# This entire section will be cached as long as the core source code does not change.

# 1.1. Install heavy, independent Python libraries.
RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu129
RUN python3 -m pip install ninja
RUN python3 -m pip install packaging
RUN python3 -m pip install flash-attn --no-build-isolation

# --- STAGE 1: Copy only dependency-related files and install them ---
# This layer will be cached as long as the dependency files do not change.
# We copy every file and directory needed for the C++/CUDA compilation,
# which is triggered by `pip install .`.
COPY requirements/ ./requirements/
COPY use_existing_torch.py ./
COPY setup.py ./
COPY pyproject.toml ./
COPY CMakeLists.txt ./
COPY MANIFEST.in ./
COPY cmake/ ./cmake/
COPY csrc/ ./csrc/
COPY vllm ./vllm
# COPY .git ./.git

ARG VERSION
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION:-0.0.0}

RUN python3 use_existing_torch.py
RUN python3 -m pip install -r requirements/build.txt
RUN python3 -m pip install -r requirements/common.txt

RUN python3 -m pip install . --no-build-isolation

# [FIX] Manually move the compiled C++/CUDA extensions from the temporary
# build directory to the final vllm package directory. This ensures that the
# Python interpreter can find them at runtime.
RUN find /app/build -name "*.so" -exec mv {} /app/vllm/ \;

RUN python3 -m pip install -U nvidia-nccl-cu12
RUN python3 -m pip install flashinfer-python
RUN python3 -m pip install librosa


# --- STAGE 2: Copy the rest of the application code ---
# Changes to these files will only invalidate the cache from this point onwards.
COPY . .

# --- STAGE 3: Final configuration ---
# Expose the application port
EXPOSE 50002

# Start the service directly
CMD ["python3", "api.py"]
