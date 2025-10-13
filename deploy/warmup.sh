#!/bin/bash
set -e

# Load the shared configuration variables
source "$(dirname "$0")/deploy.conf"

echo "--- Starting Service Warmup ---"

# Calculate the total number of containers
num_gpus=${#GPUS_TO_USE[@]}
total_containers=$((num_gpus * INSTANCES_PER_GPU))

echo "Waiting for ${total_containers} containers to initialize..."
# Add a delay to allow containers to start the web server
# sleep 15

# Construct the full path to the warmup audio file, relative to the script's location
script_dir="$(dirname "$0")"
warmup_audio_path="${script_dir}/${WARMUP_AUDIO_FILENAME}"

# Check if the warmup audio file exists
if [ ! -f "${warmup_audio_path}" ]; then
    echo "Error: Warmup audio file not found at ${warmup_audio_path}"
    exit 1
fi

port_offset=0
for gpu_id in "${GPUS_TO_USE[@]}"
do
  for (( instance=1; instance<=${INSTANCES_PER_GPU}; instance++ ))
  do
    port=$((BASE_PORT + port_offset))
    container_name="vllm-agent-asr-prod-gpu${gpu_id}-${instance}"
    health_endpoint="http://127.0.0.1:${port}/"
    asr_endpoint="http://127.0.0.1:${port}/api/v1/asr"
    
    echo "--- Preparing to warm up container ${container_name} on port ${port} ---"

    # Retry loop to wait for the service to become available
    echo "Waiting for service at ${health_endpoint} to be ready..."
    max_retries=10
    retry_interval=5
    for (( i=1; i<=max_retries; i++ )); do
        # Use curl's silent (--silent) and output-to-null (-o /dev/null) flags for a clean check
        if curl --silent -o /dev/null ${health_endpoint}; then
            echo "Service is up. Proceeding with warmup."
            break
        fi
        if [ ${i} -eq ${max_retries} ]; then
            echo "Error: Service at ${health_endpoint} did not become ready after ${max_retries} attempts."
            exit 1
        fi
        echo "Attempt ${i}/${max_retries} failed. Retrying in ${retry_interval} seconds..."
        sleep ${retry_interval}
    done

    echo "Sending warmup request to ${asr_endpoint}..."
    # Send the warmup request
    # We use a dummy API key as the request hits the container directly, bypassing Nginx.
    # The --fail flag will cause curl to exit with an error if the server returns an HTTP error.
    curl -X POST \
      -H "X-API-Key: dummy-key" \
      --fail \
      -F "files=@${warmup_audio_path}" \
      -F "keys=warmup.wav" \
      ${asr_endpoint}

    if [ $? -ne 0 ]; then
        echo "Error: Warmup request failed for container ${container_name} on port ${port}."
        echo "Check the container logs with 'sudo docker logs ${container_name}'"
    else
        echo "Container ${container_name} warmed up successfully."
    fi

    port_offset=$((port_offset + 1))
  done
done

echo "--- Warmup Complete ---"
