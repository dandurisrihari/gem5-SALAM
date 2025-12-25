#!/bin/bash
# Setup script to configure docker environment with current user's UID/GID
# Run this once before building the Docker image

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

echo "HOST_UID=$(id -u)" > "$ENV_FILE"
echo "HOST_GID=$(id -g)" >> "$ENV_FILE"

echo "Created $ENV_FILE with:"
cat "$ENV_FILE"
echo ""
echo "Now you can build and run:"
echo "  cd $SCRIPT_DIR"
echo "  docker-compose build"
echo "  docker-compose run --rm gem5-salam"
