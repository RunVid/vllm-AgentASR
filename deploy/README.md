# Deployment Instructions for vllm-AgentASR

This document outlines the step-by-step process for deploying the vllm-AgentASR service using the refactored Docker-based architecture.

## Architecture Overview

This deployment model follows modern best practices:
- **Slim Containers**: Each Docker container runs a single process (the Python application).
- **Multi-Instance Deployment**: The `docker-run-prod.sh` script launches multiple container instances, allowing for multiple instances per GPU to maximize utilization.
- **External Load Balancing**: A web server (like Nginx or Caddy) running on the **host machine** is required to act as a reverse proxy and load balancer, distributing traffic to the running containers.

## Prerequisites

1.  **Docker & NVIDIA Container Toolkit**: Ensure Docker is installed and configured to use NVIDIA GPUs.
2.  **Nginx (or Caddy)**: A web server must be installed and running on the host machine.
3.  **Git**: Required for versioning the Docker image.

---

## Deployment Workflow

### Step 1: Build the Docker Image

This step packages the application and its dependencies into a Docker image. You only need to re-run this when you change the application code or `Dockerfile`.

**Command (run from the project root `vllm-AgentASR/`):**
```bash
bash deploy/docker-build.sh
```

### Step 2: Configure & Run the Containers

This step launches the Docker containers based on the image built in Step 1.

1.  **(Optional) Customize Deployment**: Before running, you can edit `deploy/docker-run-prod.sh` to configure:
    - `GPUS_TO_USE`: An array of GPU IDs to deploy on (e.g., `(0 1)`).
    - `INSTANCES_PER_GPU`: The number of containers to run on each GPU (e.g., `2`).
    - `BASE_PORT`: The starting port on the host for the containers (e.g., `52000`).

2.  **Launch Containers**:
    **Command (run from the project root `vllm-AgentASR/`):**
    ```bash
    bash deploy/docker-run-prod.sh
    ```

### Step 3: Configure the Host Load Balancer

This is a one-time setup to tell your host's Nginx how to find and distribute traffic to your running containers. The provided `vllm_load_balancer.conf` is configured for the default settings in the run script. If you change the ports or number of instances, you must update it accordingly.

**Commands (run from your workspace root):**
```bash
# 1. Copy the configuration file to Nginx's "sites-available" directory.
sudo cp vllm-AgentASR/deploy/vllm_load_balancer.conf /etc/nginx/sites-available/

# 2. Clean up any old links/files and enable the site by creating the correct symbolic link.
#    Note: We create the link named "vllm_load_balancer" (without .conf) to match
#    the include directive in the main nginx.conf on this system.
sudo rm -f /etc/nginx/sites-enabled/vllm_load_balancer
sudo rm -f /etc/nginx/sites-enabled/vllm_load_balancer.conf
sudo ln -s /etc/nginx/sites-available/vllm_load_balancer.conf /etc/nginx/sites-enabled/vllm_load_balancer

# 3. Test the Nginx configuration for errors.
sudo nginx -t

# 4. If the test is successful, restart Nginx to apply the changes.
sudo systemctl restart nginx
```

### Step 4: Warm Up the Services

After the containers are running, it is recommended to run the warmup script. This script sends a dummy request to each container, which triggers the one-time compilation of the model's GPU kernels. This prevents the first real user request from experiencing a "cold start" delay.

**Command (run from the project root `vllm-AgentASR/`):**
```bash
bash deploy/warmup.sh
```

### Step 5: Verify the Service

1.  **Check Running Containers**:
    ```bash
    docker ps
    ```
    You should see all your configured containers running (e.g., `vllm-agent-asr-prod-gpu0-1`, etc.).

2.  **Send a Test Request**:
    Use a `curl` command to send a test audio file. Remember to replace `YOUR_SERVER_IP` and the file path.
    ```bash
    curl -X POST \
    -H "X-API-Key: 6a033ce8d2c5346516741b9c38965e633b9a348d0999a31d957141e11d572f57" \
    --insecure \
    -F "files=@/path/to/your/audio.wav" \
    -F "keys=my-audio-file.wav" \
    https:///8.34.125.71:8443/api/v1/asr
    ```

---

## Stopping the Service

To stop the application, you need to stop the running Docker containers. The `docker-run-prod.sh` script will automatically remove containers with the same name on the next run, but for a clean stop, you can use `docker stop` or `docker rm -f`.
```bash
# Example for a single container
docker stop vllm-agent-asr-prod-gpu0-1

# Or to stop all of them (use with caution)
docker stop $(docker ps -q --filter name=vllm-agent-asr-prod)
```
