#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YGO_AGENT="$ROOT/references/ygo-agent"
CORE="$ROOT/references/ygopro-core"
LUA="$CORE/lua"
DEPS="$ROOT/references/build-deps"
PATCHER="$ROOT/scripts/patch_edopro_adapter.py"
BUILD_DIR="$ROOT/tmp/build-edopro-modern"
OVERLAY="$BUILD_DIR/overlay"
INCLUDE_DIR="$BUILD_DIR/include"
OUTPUT="$BUILD_DIR/edopro_ygoenv.so"
OBJECT_DIR="$BUILD_DIR/objects"
CXX="${CXX:-g++-12}"

if [[ "${CONDA_DEFAULT_ENV:-}" != "ygo" ]]; then
  echo "ERROR: activate the 'ygo' Conda environment before building edopro_ygoenv." >&2
  exit 2
fi

if ! PYTHON="$(command -v python)"; then
  echo "ERROR: Python is not available in the active 'ygo' environment." >&2
  exit 1
fi
for command in "$CXX" find ldd sha256sum sort; do
  if ! command -v "$command" >/dev/null; then
    echo "ERROR: required build command not found: $command" >&2
    exit 1
  fi
done
if [[ "$($CXX -dumpfullversion -dumpversion)" != 12.* ]]; then
  echo "ERROR: modern runtime builds require GCC 12.x: $CXX" >&2
  exit 1
fi

required=(
  "$YGO_AGENT/ygoenv/ygoenv/edopro/edopro.cpp"
  "$YGO_AGENT/ygoenv/ygoenv/edopro/edopro.h"
  "$CORE/ocgapi.cpp"
  "$CORE/ocgapi.h"
  "$LUA/luaconf-customize.h"
  "$LUA/src/lua.h"
  "$DEPS/fmt/src/format.cc"
  "$DEPS/SQLiteCpp/src/Database.cpp"
  "$DEPS/unordered_dense/include/ankerl/unordered_dense.h"
  "$PATCHER"
)
for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "ERROR: missing modern runtime build input: $path" >&2
    exit 1
  fi
done

if ! grep -q '^#define OCG_VERSION_MAJOR 11$' "$CORE/ocgapi_types.h"; then
  echo "ERROR: adapter patch targets EDOPro core API major version 11." >&2
  exit 1
fi

PY_INCLUDE="$($PYTHON -c 'import sysconfig; print(sysconfig.get_path("include"))')"
if [[ ! -f "$PY_INCLUDE/Python.h" ]]; then
  echo "ERROR: Python headers not found under $PY_INCLUDE" >&2
  exit 1
fi
mkdir -p "$OVERLAY/ygoenv/edopro" "$INCLUDE_DIR"
"$PYTHON" "$PATCHER" \
  --source "$YGO_AGENT/ygoenv/ygoenv/edopro/edopro.h" \
  --output "$OVERLAY/ygoenv/edopro/edopro.h"
ln -sfn "$CORE" "$INCLUDE_DIR/edopro-core"

mapfile -t CORE_SOURCES < <(find "$CORE" -maxdepth 1 -name '*.cpp' -print | sort)
mapfile -t LUA_SOURCES < <(
  find "$LUA/src" -maxdepth 1 -name '*.c' \
    ! -name 'lcorolib.c' \
    ! -name 'ldblib.c' \
    ! -name 'linit.c' \
    ! -name 'loadlib.c' \
    ! -name 'loslib.c' \
    ! -name 'ltests.c' \
    ! -name 'lua.c' \
    ! -name 'luac.c' \
    ! -name 'lutf8lib.c' \
    ! -name 'onelua.c' \
    -print | sort
)
mapfile -t SQLITECPP_SOURCES < <(find "$DEPS/SQLiteCpp/src" -maxdepth 1 -name '*.cpp' -print | sort)

COMPILE_FLAGS=(
  -std=c++17 -O2 -DNDEBUG -march=native -fPIC
  -fvisibility=hidden -fvisibility-inlines-hidden
  -I"$OVERLAY"
  -I"$YGO_AGENT/ygoenv"
  -I"$INCLUDE_DIR"
  -I"$LUA/src"
  -include "$LUA/luaconf-customize.h"
  -I"$DEPS/fmt/include"
  -I"$DEPS/SQLiteCpp/include"
  -I"$DEPS/unordered_dense/include"
  -I"$PY_INCLUDE"
)
SOURCES=(
  "$YGO_AGENT/ygoenv/ygoenv/edopro/edopro.cpp"
  "${CORE_SOURCES[@]}"
  "${LUA_SOURCES[@]}"
  "${SQLITECPP_SOURCES[@]}"
  "$DEPS/fmt/src/format.cc"
  "$DEPS/fmt/src/os.cc"
)

mkdir -p "$OBJECT_DIR"
OBJECTS=()
echo "Compiling edopro_ygoenv as ${#SOURCES[@]} separate translation units..."
for index in "${!SOURCES[@]}"; do
  source="${SOURCES[$index]}"
  object="$OBJECT_DIR/$(printf '%03d.o' "$index")"
  "$CXX" "${COMPILE_FLAGS[@]}" -c "$source" -o "$object"
  OBJECTS+=("$object")
done

echo "Linking ${#OBJECTS[@]} objects into $OUTPUT..."
"$CXX" -shared "${OBJECTS[@]}" -Wl,--exclude-libs,ALL \
  /usr/lib/x86_64-linux-gnu/libsqlite3.a \
  -lglog -lgflags -lunwind -pthread -ldl -lm \
  -o "$OUTPUT"

sha256sum "$OUTPUT"
ldd "$OUTPUT"
"$PYTHON" - "$OUTPUT" <<'PY'
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

extension = Path(sys.argv[1]).resolve()
spec = spec_from_file_location("edopro_ygoenv", extension)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to create import spec for {extension}")

module = module_from_spec(spec)
spec.loader.exec_module(module)
required = {"_EDOProEnvPool", "_EDOProEnvSpec", "init_module"}
missing = sorted(required.difference(dir(module)))
if missing:
    raise RuntimeError(f"Missing extension exports: {missing}")
print(f"Verified Python extension exports: {','.join(sorted(required))}")
PY
