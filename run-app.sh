#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

exec .venv/bin/python bot.py -t twilio -x 2human.ngrok.io --port 3002
