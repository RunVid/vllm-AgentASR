#!/bin/bash
set -e

# This script launches multiple container instances for each specified GPU.
# You still need an external load balancer (like Nginx or Caddy on the host)
# to distribute traffic to the different host ports.

# Use the git commit hash as the version tag if VERSION is not set
if [ -z "${VERSION}" ]; then
  export VERSION=$(git rev-parse --short HEAD)
  echo "VERSION not set, using git commit: ${VERSION}"
fi

# --- Configuration ---
# Define the specific GPUs to use
GPUS_TO_USE=(0)
# Define how many container instances to run on EACH GPU
INSTANCES_PER_GPU=2
BASE_PORT=52000
IMAGE_NAME="19pine/vllm-agent-asr" # Change this to your desired image name
# --- End Configuration ---

echo "Using GPUs: ${GPUS_TO_USE[*]}"
echo "Instances per GPU: ${INSTANCES_PER_GPU}"
echo "Base port: ${BASE_PORT}"
echo "Image: ${IMAGE_NAME}:${VERSION}"

port_offset=0
for gpu_id in "${GPUS_TO_USE[@]}"
do
  for (( instance=1; instance<=${INSTANCES_PER_GPU}; instance++ ))
  do
    port=$((BASE_PORT + port_offset))
    container_name="vllm-agent-asr-prod-gpu${gpu_id}-${instance}"

    echo "--> Launching container ${container_name} on GPU ${gpu_id}, mapping host port ${port} to container port 50002"

    # Stop and remove any existing container with the same name
    docker rm -f ${container_name} || true

    # Run the new container
    docker run -d \
      --name ${container_name} \
      --gpus device=${gpu_id} \
      -p "127.0.0.1:${port}:50002" \
      ${IMAGE_NAME}:${VERSION}

    port_offset=$((port_offset + 1))
  done
done

echo ""
echo "All containers have been started."
echo "You can check their status with 'docker ps'."
