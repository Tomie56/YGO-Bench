#!/usr/bin/env bash
set -euo pipefail

ROOT=/mnt/d/Tomie
PREFIX="$ROOT/.wsl-linux/miniconda3"
INSTALLER="$ROOT/Miniconda3-latest-Linux-x86_64.sh"
URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
# Miniconda3-py314_26.5.3-2, published 2026-07-29 in Anaconda's official index.
EXPECTED_SHA256=80bc27f13c4de90f10e387aa45e864de4f0860692c1221aef5900009a2b55302

mkdir -p "$ROOT"

if [[ -e "$PREFIX" && ! -x "$PREFIX/bin/conda" ]]; then
  echo "ERROR: $PREFIX exists but is not a valid Miniconda installation." >&2
  exit 2
fi

if [[ ! -x "$PREFIX/bin/conda" ]]; then
  echo "[1/4] Checking Linux Miniconda installer"
  current_sha256=""
  if [[ -f "$INSTALLER" ]]; then
    current_sha256=$(sha256sum "$INSTALLER" | awk '{print $1}')
  fi
  if [[ "$current_sha256" != "$EXPECTED_SHA256" ]]; then
    echo "Downloading or resuming $INSTALLER"
    curl -fL -C - --retry 10 --retry-all-errors --retry-delay 3 \
      --speed-limit 1024 --speed-time 30 -o "$INSTALLER" "$URL"
  else
    echo "Reusing complete installer at $INSTALLER"
  fi

  echo "[2/4] Verifying SHA256"
  actual=$(sha256sum "$INSTALLER" | awk '{print $1}')
  if [[ "$EXPECTED_SHA256" != "$actual" ]]; then
    echo "ERROR: Miniconda installer checksum mismatch." >&2
    echo "expected=$EXPECTED_SHA256" >&2
    echo "actual=$actual" >&2
    exit 3
  fi
  echo "sha256=$actual"

  echo "[3/4] Installing base environment to $PREFIX"
  bash "$INSTALLER" -b -p "$PREFIX"
else
  echo "[1-3/4] Reusing existing Miniconda at $PREFIX"
fi

echo "[4/4] Initializing bash"
"$PREFIX/bin/conda" init bash
"$PREFIX/bin/conda" config --set auto_activate_base true

# Verify without relying on interactive shell initialization.
source "$PREFIX/etc/profile.d/conda.sh"
conda activate base

echo "--- base environment ---"
conda --version
python --version
python -c 'import sys; print(sys.executable)'

echo "--- NVIDIA driver visible in WSL ---"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
else
  echo "nvidia-smi not found"
fi

echo "--- WSL CUDA driver interface ---"
if compgen -G '/usr/lib/wsl/lib/libcuda.so*' >/dev/null; then
  ls -l /usr/lib/wsl/lib/libcuda.so*
else
  echo "WSL libcuda not found"
fi

echo "--- Linux CUDA toolkit ---"
if command -v nvcc >/dev/null 2>&1; then
  nvcc --version
else
  echo "nvcc not installed in Ubuntu"
fi
