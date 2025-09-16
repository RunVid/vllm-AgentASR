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
ENV TORCH_CUDA_ARCH_LIST="8.0;8.6;8.9;9.0;9.1"
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# --- STAGE 1: Build the stable, unchanging core dependencies ---
# This entire section will be cached as long as the core source code does not change.

# 1.1. Install heavy, independent Python libraries.
RUN python3 -m pip install --upgrade pip
RUN python3 -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu129
RUN python3 -m pip install ninja
RUN python3 -m pip install -v -U git+https://github.com/facebookresearch/xformers.git@main#egg=xformers

# 1.2. Copy all source code *except* the frequently changing parts.
COPY . .
RUN rm -rf deploy api.py

# 1.3. Install requirements and the vllm package itself.
RUN python3 -m pip install -r requirements/build.txt
RUN python3 -m pip install -r requirements/common.txt
RUN python3 use_existing_torch.py
RUN python3 -m pip install . --no-build-isolation
RUN python3 -m pip install -U nvidia-nccl-cu12
RUN python3 -m pip install flashinfer-python
RUN python3 -m pip install librosa

# --- STAGE 2: Add the frequently changing application code ---
# Changes to these files will only invalidate the cache from this point onwards.
COPY deploy/ ./deploy/
COPY api.py ./

# --- STAGE 3: Final configuration ---
# Generate self-signed SSL certificate for Nginx
RUN mkdir -p /etc/nginx/ssl
RUN openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/self-signed.key \
    -out /etc/nginx/ssl/self-signed.crt \
    -subj "/C=US/ST=CA/L=SF/O=Org/CN=localhost"

# Copy the Nginx configuration and enable the site
# Note: This assumes vllm_load_balancer.conf is inside the deploy directory
COPY deploy/vllm_load_balancer.conf /etc/nginx/sites-available/vllm_load_balancer
RUN ln -s /etc/nginx/sites-available/vllm_load_balancer /etc/nginx/sites-enabled/ && \
    rm /etc/nginx/sites-enabled/default

# Copy the supervisor configuration file
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose the HTTPS port
EXPOSE 443

# Start supervisor to manage Nginx and the application
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
