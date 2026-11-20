#!/bin/bash
set -e
cd "$(dirname "$0")"
PYTHON=python3
$PYTHON -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
