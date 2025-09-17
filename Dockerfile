# Base image with CUDA 12.9.0 support
FROM nvidia/cuda:12.9.0-devel-ubuntu22.04

# Set non-interactive frontend for package installers
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    python3.10 \
    python3-pip \
    nginx \
    supervisor \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Set environment variables
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
COPY .git ./.git
COPY cmake/ ./cmake/
COPY csrc/ ./csrc/
COPY vllm ./vllm

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
# Generate self-signed SSL certificate for Nginx
RUN mkdir -p /etc/nginx/ssl
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/self-signed.key \
    -out /etc/nginx/ssl/self-signed.crt \
    -subj "/C=US/ST=CA/L=SF/O=Org/CN=localhost"

# The Nginx configuration will be generated dynamically at runtime by run.sh.
# We no longer copy a static config file during the build.
# COPY deploy/vllm_load_balancer.conf /etc/nginx/sites-available/vllm_load_balancer
# RUN ln -s /etc/nginx/sites-available/vllm_load_balancer /etc/nginx/sites-enabled/ && \
#     rm /etc/nginx/sites-enabled/default

# Copy the supervisor configuration file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose the HTTPS port
EXPOSE 443

# Start supervisor to manage Nginx and the application
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
