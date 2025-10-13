#!/bin/bash
set -e

# This script builds the Docker image for the vllm-AgentASR application.
# It should be run from the root of the vllm-AgentASR project directory.

IMAGE_NAME="19pine/vllm-agent-asr" # Change this to your desired image name

if [ -z "${VERSION}" ]; then
  export VERSION=$(git rev-parse --short HEAD)
  echo "VERSION not set, using git commit: ${VERSION}"
fi

echo "Building Docker image ${IMAGE_NAME}:${VERSION}..."

docker build -t "${IMAGE_NAME}:${VERSION}" -f deploy/Dockerfile .

echo "Build complete."
