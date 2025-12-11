#!/bin/bash
set -e

# Load shared configuration
source "$(dirname "$0")/deploy.conf"

# IMAGE_TAG: for Docker image tag (can be git hash)
# VERSION: for Python package version (must be PEP 440)
IMAGE_FULL="${IMAGE_NAME}:${IMAGE_TAG}"

echo "============================================"
echo "Docker Image: ${IMAGE_FULL}"
echo "Python Version: ${VERSION}"
echo "============================================"

# Parse arguments
FORCE_BUILD=false
NO_PUSH=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE_BUILD=true
            shift
            ;;
        --no-push)
            NO_PUSH=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --force     Force rebuild even if image exists in registry"
            echo "  --no-push   Skip pushing after build"
            echo "  -h, --help  Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Step 1: Try to pull (unless --force)
if [ "$FORCE_BUILD" = false ]; then
    echo ""
    echo "[Step 1] Checking if image exists in registry..."
    if docker pull "${IMAGE_FULL}" 2>/dev/null; then
        echo ""
        echo "✅ Image already exists, skipped building."
        exit 0
    fi
    echo "   Image not found, will build."
else
    echo ""
    echo "[Step 1] Skipped (--force), will build."
fi

# Step 2: Build
echo ""
echo "[Step 2] Building..."
docker build \
  --build-arg "VERSION=${VERSION}" \
  -t "${IMAGE_FULL}" \
  -f deploy/Dockerfile .

echo ""
echo "✅ Build complete: ${IMAGE_FULL}"

# Step 3: Push (default behavior, skip with --no-push)
if [ "$NO_PUSH" = false ]; then
    echo ""
    echo "[Step 3] Pushing to registry..."
    docker push "${IMAGE_FULL}"
    echo "✅ Push complete."
else
    echo ""
    echo "[Step 3] Skipped push (--no-push)."
    echo "   Manual push: docker push ${IMAGE_FULL}"
fi
