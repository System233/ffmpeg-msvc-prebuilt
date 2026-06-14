#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export VCPKG_OVERLAY_PORTS="${SCRIPT_DIR}/ports"
export VCPKG_OVERLAY_TRIPLETS="${SCRIPT_DIR}/triplets"