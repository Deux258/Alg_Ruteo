#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
mkdir -p renders
if [[ ! -x node_modules/.bin/hyperframes ]]; then
  npm install --no-audit --no-fund
fi
npm run prepare:assets
node_modules/.bin/hyperframes doctor
node_modules/.bin/hyperframes check --json > renders/hyperframes-check.json
node_modules/.bin/hyperframes snapshot --at 2,7,13,20,28,36,43,49,56
npm run preview
npm run render
ffprobe -v error -show_format -show_streams -of json renders/Alg_Ruteo_Hyperframes.mp4 > renders/hyperframes-probe.json
printf '%s\n' 'Video local: renders/Alg_Ruteo_Hyperframes.mp4'
