#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
umask 077
python3 -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12+ vereist"'
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
if [[ ! -f .venv/requirements.installed ]] || ! cmp -s requirements.txt .venv/requirements.installed; then
  # CPU embeddings: avoid downloading unused CUDA libraries.
  .venv/bin/python -m pip install 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu
  .venv/bin/python -m pip install -r requirements.txt
  cp requirements.txt .venv/requirements.installed
fi
if [[ ! -f .env ]]; then cp .env.example .env; fi
exec .venv/bin/python -m uvicorn server.main:create_app --factory --host 127.0.0.1 --port 8765 --no-access-log
