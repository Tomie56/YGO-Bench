#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YGO_AGENT="$ROOT/references/ygo-agent"
DEPS="$ROOT/references/build-deps"
BUILD_DIR="$ROOT/tmp/build-ygoenv"
RESULT_DIR="$ROOT/results/cpu_pilot/build"
OUTPUT="$YGO_AGENT/ygoenv/ygoenv/ygopro/ygopro_ygoenv.so"
CXX="${CXX:-g++}"

if [[ "${CONDA_DEFAULT_ENV:-}" != "ygo" ]]; then
  echo "ERROR: activate the 'ygo' Conda environment before building ygoenv." >&2
  exit 2
fi

PYTHON="$(command -v python)"

required=(
  "$DEPS/ygopro-core/ocgapi.cpp"
  "$DEPS/fmt/src/format.cc"
  "$DEPS/SQLiteCpp/src/Database.cpp"
  "$DEPS/unordered_dense/include/ankerl/unordered_dense.h"
  "$YGO_AGENT/ygoenv/ygoenv/ygopro/ygopro.cpp"
)
for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing build input: $path" >&2
    exit 1
  fi
done

PY_INCLUDE="$($PYTHON -c 'import sysconfig; print(sysconfig.get_path("include"))')"
mkdir -p "$BUILD_DIR" "$RESULT_DIR"

if [[ -f "$OUTPUT" && ! -f "$RESULT_DIR/ygopro_ygoenv.pre-card-id-fix.so" ]]; then
  cp "$OUTPUT" "$RESULT_DIR/ygopro_ygoenv.pre-card-id-fix.so"
fi

mapfile -t CORE_SOURCES < <(find "$DEPS/ygopro-core" -maxdepth 1 -name '*.cpp' -print | sort)
mapfile -t SQLITECPP_SOURCES < <(find "$DEPS/SQLiteCpp/src" -maxdepth 1 -name '*.cpp' -print | sort)

TEMP_OUTPUT="$BUILD_DIR/ygopro_ygoenv.so"
echo "Compiling ygopro_ygoenv with ${#CORE_SOURCES[@]} core sources and ${#SQLITECPP_SOURCES[@]} SQLiteCpp sources..."
"$CXX" \
  -std=c++17 -O3 -flto -DNDEBUG -march=native -fPIC \
  -fvisibility=hidden -fvisibility-inlines-hidden \
  -shared \
  -I"$YGO_AGENT/ygoenv" \
  -I"$DEPS" \
  -I"$DEPS/fmt/include" \
  -I"$DEPS/SQLiteCpp/include" \
  -I"$DEPS/unordered_dense/include" \
  -I"$PY_INCLUDE" \
  -I/usr/include/lua5.3 \
  "$YGO_AGENT/ygoenv/ygoenv/ygopro/ygopro.cpp" \
  "${CORE_SOURCES[@]}" \
  "${SQLITECPP_SOURCES[@]}" \
  "$DEPS/fmt/src/format.cc" \
  "$DEPS/fmt/src/os.cc" \
  -Wl,--exclude-libs,ALL \
  /usr/lib/x86_64-linux-gnu/libsqlite3.a \
  -llua5.3 -lglog -lgflags -lunwind -pthread -ldl -lm \
  -o "$TEMP_OUTPUT"

cp "$TEMP_OUTPUT" "$OUTPUT"
sha256sum "$RESULT_DIR/ygopro_ygoenv.pre-card-id-fix.so" "$OUTPUT"
ldd "$OUTPUT"
