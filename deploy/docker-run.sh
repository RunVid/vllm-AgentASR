#!/bin/bash
set -e

# Check if environment parameter is provided
if [ "$#" -ne 1 ] || { [ "$1" != "prod" ] && [ "$1" != "staging" ]; }; then
    echo "Usage: $0 {prod|staging}"
    echo ""
    echo "Examples:"
    echo "  $0 prod      # Deploy to production environment"
    echo "  $0 staging   # Deploy to staging environment"
    exit 1
fi

ENV=$1

# Load the shared configuration variables
source "$(dirname "$0")/deploy.conf"

# Set environment-specific variables
if [ "${ENV}" == "prod" ]; then
    BASE_PORT=${BASE_PORT_PROD}
    GPUS_TO_USE=("${GPUS_TO_USE_PROD[@]}")
    INSTANCES_PER_GPU=${INSTANCES_PER_GPU_PROD}
    CONTAINER_PREFIX="vllm-agent-asr-prod"
else
    BASE_PORT=${BASE_PORT_STAGING}
    GPUS_TO_USE=("${GPUS_TO_USE_STAGING[@]}")
    INSTANCES_PER_GPU=${INSTANCES_PER_GPU_STAGING}
    CONTAINER_PREFIX="vllm-agent-asr-staging"
fi

# This script launches multiple container instances for each specified GPU.
# You still need an external load balancer (like Nginx or Caddy on the host)
# to distribute traffic to the different host ports.

echo "Environment: ${ENV}"
echo "Using GPUs: ${GPUS_TO_USE[*]}"
echo "Instances per GPU: ${INSTANCES_PER_GPU}"
echo "Base port: ${BASE_PORT}"
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"

port_offset=0
# Loop through each instance number
for (( instance=1; instance<=${INSTANCES_PER_GPU}; instance++ ))
do
  # Loop through each GPU ID
  for gpu_id in "${GPUS_TO_USE[@]}"
  do
    port=$((BASE_PORT + port_offset))
    container_name="${CONTAINER_PREFIX}-gpu${gpu_id}-${instance}"

    echo "--> Launching container ${container_name} on GPU ${gpu_id}, mapping host port ${port}"

    # Stop and remove any existing container with the same name before launching.
    sudo docker rm -f ${container_name} || true
    echo "HF_TOKEN: ${HF_TOKEN}"
    # Run the new container
    sudo docker run -d \
      --name ${container_name} \
      --restart always \
      --gpus device=${gpu_id} \
      -e "MODEL_PATH=${MODEL_PATH}" \
      -e "HF_TOKEN=${HF_TOKEN}" \
      -v "${HF_CACHE_DIR}:/root/.cache/huggingface" \
      -p "127.0.0.1:${port}:50002" \
      --ipc=host \
      ${IMAGE_NAME}:${IMAGE_TAG}

    port_offset=$((port_offset + 1))
  done

  # Wait for 2 minutes before starting the next set of instances on the GPUs,
  # but don't wait after the last instance.
  if [ "${instance}" -lt "${INSTANCES_PER_GPU}" ]; then
      echo "--> Waiting for 2 minutes before launching the next instance on each GPU..."
      sleep 120
  fi
done

echo "--> All ${ENV} containers launched."

echo ""
echo "All containers have been started."
echo "You can check their status with 'docker ps'."

