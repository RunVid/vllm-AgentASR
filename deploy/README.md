# Deployment Instructions for vllm-AgentASR

This document outlines the step-by-step process for deploying the vllm-AgentASR service using the refactored Docker-based architecture.

## Architecture Overview

This deployment model follows modern best practices:
- **Slim Containers**: Each Docker container runs a single process (the Python application).
- **Multi-Instance Deployment**: The `docker-run-prod.sh` script launches multiple container instances, allowing for multiple instances per GPU to maximize utilization.
- **External Load Balancing**: A web server (like Nginx or Caddy) running on the **host machine** is required to act as a reverse proxy and load balancer, distributing traffic to the running containers.
- **Shared Configuration**: Deployment settings are centralized in `deploy/deploy.conf`.

## Prerequisites

1.  **Docker & NVIDIA Container Toolkit**: Ensure Docker is installed and configured to use NVIDIA GPUs.
2.  **Nginx (or Caddy)**: A web server must be installed and running on the host machine.
3.  **Git**: Required for versioning the Docker image.

---

## Deployment Workflow

### Step 1: Configure Your Deployment

All deployment settings are controlled by the `deploy/deploy.conf` file. Before you begin, open this file and customize it for your environment if needed.

### Step 2: Build the Docker Image

This step packages the application and its dependencies into a Docker image. You only need to re-run this when you change the application code or `Dockerfile`.

**Command (run from the project root `vllm-AgentASR/`):**
```bash
bash deploy/docker-build.sh
```

### Step 3: Run the Containers

This step launches the Docker containers based on the settings in `deploy/deploy.conf`.

**Command (run from the project root `vllm-AgentASR/`):**
```bash
bash deploy/docker-run-prod.sh
```

### Step 4: Configure the Host Load Balancer

This is a one-time setup to tell your host's Nginx how to find and distribute traffic to your running containers. The provided `vllm_load_balancer.conf` is configured for the default settings. If you change the ports or number of instances, you must update it accordingly.

**Commands:**
```bash
# 1. Copy the configuration file to Nginx's "sites-available" directory.
sudo cp vllm-AgentASR/deploy/vllm_load_balancer.conf /etc/nginx/sites-available/

# 2. Clean up any old links/files and enable the site by creating the correct symbolic link.
sudo rm -f /etc/nginx/sites-enabled/vllm_load_balancer
sudo rm -f /etc/nginx/sites-enabled/vllm_load_balancer.conf
sudo ln -s /etc/nginx/sites-available/vllm_load_balancer.conf /etc/nginx/sites-enabled/vllm_load_balancer

# 3. Test the Nginx configuration for errors.
sudo nginx -t

# 4. If the test is successful, restart Nginx to apply the changes.
sudo systemctl restart nginx
```

### Step 5: Warm Up the Services

After the containers are running, run the warmup script to prevent a "cold start" delay for the first user.

**Command (run from the project root `vllm-AgentASR/`):**
```bash
bash deploy/warmup.sh
```

### Step 6: Verify the Service

1.  **Check Running Containers**:
    ```bash
    docker ps
    ```

2.  **Send a Test Request**:
    Use a `curl` command to send a test audio file. Remember to replace `YOUR_SERVER_IP` and the file path.
    ```bash
    curl -X POST \
    -H "X-API-Key: 6a033ce8d2c5346516741b9c38965e633b9a348d0999a31d957141e11d572f57" \
    --insecure \
    -F "files=@/path/to/your/audio.wav" \
    -F "keys=my-audio-file.wav" \
    https://YOUR_SERVER_IP:8443/api/v1/asr
    ```

---

## Stopping the Service

To stop the application, you need to stop the running Docker containers. You can do this by re-running the launch script (which will stop and remove the old ones before starting new ones) or by using `docker stop`.
```bash
# To stop all project-related containers
docker stop $(docker ps -q --filter name=vllm-agent-asr-prod)
```
