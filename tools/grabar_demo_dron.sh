#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
command -v node >/dev/null || { echo 'Falta Node.js.' >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo 'Falta FFmpeg.' >&2; exit 1; }
command -v ffprobe >/dev/null || { echo 'Falta FFprobe.' >&2; exit 1; }
exec node tools/demo_perspectivas/grabar.mjs "$@"
