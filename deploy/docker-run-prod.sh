#!/bin/bash
set -e

# Load the shared configuration variables
source "$(dirname "$0")/deploy.conf"

# This script launches multiple container instances for each specified GPU.
# You still need an external load balancer (like Nginx or Caddy on the host)
# to distribute traffic to the different host ports.

# Use the git commit hash as the version tag if VERSION is not set
if [ -z "${VERSION}" ]; then
  export VERSION=$(git rev-parse --short HEAD)
  echo "VERSION not set, using git commit: ${VERSION}"
fi

echo "Using GPUs: ${GPUS_TO_USE[*]}"
echo "Instances per GPU: ${INSTANCES_PER_GPU}"
echo "Base port: ${BASE_PORT}"
echo "Image: ${IMAGE_NAME}:${VERSION}"
echo "Model: ${MODEL_NAME}"

port_offset=0
for gpu_id in "${GPUS_TO_USE[@]}"
do
  for (( instance=1; instance<=${INSTANCES_PER_GPU}; instance++ ))
  do
    port=$((BASE_PORT + port_offset))
    container_name="vllm-agent-asr-prod-gpu${gpu_id}-${instance}"

    echo "--> Launching container ${container_name} on GPU ${gpu_id}, mapping host port ${port}"

    # Construct the full path to the model directory on the host
    host_model_dir="${HOST_CHECKPOINTS_DIR}/${MODEL_NAME}"

    # Check if the host model directory exists
    if [ ! -d "${host_model_dir}" ]; then
        echo "Error: Model directory not found on host at ${host_model_dir}"
        exit 1
    fi

    # Stop and remove any existing container with the same name before launching.
    sudo docker rm -f ${container_name} || true

    # Run the new container
    sudo docker run -d \
      --name ${container_name} \
      --gpus device=${gpu_id} \
      -v "${host_model_dir}:${CONTAINER_MODEL_PATH}:ro" \
      -e "MODEL_PATH=${CONTAINER_MODEL_PATH}" \
      -p "127.0.0.1:${port}:50002" \
      ${IMAGE_NAME}:${VERSION}

    port_offset=$((port_offset + 1))
  done
done

echo ""
echo "All containers have been started."
echo "You can check their status with 'docker ps'."
