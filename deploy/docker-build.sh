#!/bin/bash
set -e

# Load shared configuration to get the image name and version
source "$(dirname "$0")/deploy.conf"

echo "Building Docker image ${IMAGE_NAME}:${VERSION}..."

docker build \
  --build-arg "VERSION=${VERSION}" \
  -t "${IMAGE_NAME}:${VERSION}" \
  -f deploy/Dockerfile .

echo "Build complete."
