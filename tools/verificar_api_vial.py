"""Comprueba la API HTTP real (sin dependencias externas ni mutaciones)."""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--unreachable", required=True)
    args = parser.parse_args()
    base = args.url.rstrip("/")
    checks = []

    def get(path, expected=200):
        try:
            with urlopen(base + path, timeout=45) as response:
                code = response.status
                value = json.load(response)
        except HTTPError as exc:
            code = exc.code
            value = json.load(exc)
        assert code == expected, (path, code, value)
        checks.append(dict(path=path, status=code, response=value))
        return value

    health = get("/health")
    assert health["routing_ready"]
    p = health["base"]["road_origin"]["coordinates"]
    nearest = get(f"/api/nodo?lon={p[0]}&lat={p[1]}")
    assert nearest["id"] == health["base"]["node_id"]
    get("/api/nodo?lon=-71.5&lat=-33.05", 422)
    get("/api/ruta?destino=abc", 422)
    get("/api/ruta?destino=" + args.unreachable, 422)
    proof = dict(
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        url=base,
        successful=True,
        checks=checks,
    )
    args.output.write_text(
        json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(checks)} comprobaciones HTTP correctas; run " + health["run_id"])


if __name__ == "__main__":
    main()
