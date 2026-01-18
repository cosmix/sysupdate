#!/usr/bin/env bash
set -euo pipefail

PYAPP_VERSION="0.22.0"
PYAPP_DIR=".pyapp-src"

# Parse args
EMBED_PYTHON=0
while [[ $# -gt 0 ]]; do
    case $1 in
        --embed) EMBED_PYTHON=1; shift ;;
        *) echo "Usage: $0 [--embed]"; exit 1 ;;
    esac
done

# Check for Rust
if ! command -v cargo &> /dev/null; then
    echo "Error: Rust not installed. Run:"
    echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi

# Build wheel
echo "Building wheel..."
uv build --wheel

WHEEL_PATH=$(ls dist/*.whl | head -1)
echo "Built: $WHEEL_PATH"

# Download PyApp if needed
if [[ ! -d "$PYAPP_DIR" ]]; then
    echo "Downloading PyApp v${PYAPP_VERSION}..."
    curl -Lo pyapp.tar.gz "https://github.com/ofek/pyapp/releases/download/v${PYAPP_VERSION}/source.tar.gz"
    tar -xzf pyapp.tar.gz
    mv "pyapp-v${PYAPP_VERSION}" "$PYAPP_DIR"
    rm pyapp.tar.gz
fi

# Build binary
echo "Building binary (embed_python=$EMBED_PYTHON)..."
cd "$PYAPP_DIR"

PYAPP_PROJECT_NAME=sysupdate \
PYAPP_PROJECT_PATH="$(realpath "../$WHEEL_PATH")" \
PYAPP_EXEC_SPEC="sysupdate.__main__:main" \
PYAPP_PYTHON_VERSION="3.11" \
PYAPP_FULL_ISOLATION="true" \
PYAPP_PIP_EXTERNAL="true" \
PYAPP_DISTRIBUTION_EMBED="$EMBED_PYTHON" \
cargo build --release

cd ..
cp "$PYAPP_DIR/target/release/pyapp" sysupdate-local
chmod +x sysupdate-local

echo ""
echo "Done: ./sysupdate-local"
ls -lh sysupdate-local
