"""Reintenta el PDF oficial sin sustituir el manifiesto ni cambiar restricciones publicadas."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    source = json.loads(Path("datos/entrada/aereo_v2/manifest.json").read_text())[
        "sources"
    ]["S6"]
    report = dict(
        recorded_at_utc=datetime.now(timezone.utc).isoformat(),
        url=source["url"],
        original_sha256=source["sha256"],
        active_manifest_modified=False,
    )
    try:
        with urlopen(
            Request(source["url"], headers={"User-Agent": "UDP-Ruteo-Academico/3.0"}),
            timeout=25,
        ) as response:
            raw = response.read()
            report["http_status"] = response.status
        report.update(
            bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            is_pdf=raw.startswith(b"%PDF"),
        )
        if not report["is_pdf"]:
            raise ValueError("La respuesta no es un PDF")
        name = "AIP_verificacion_" + report["sha256"][:16] + ".pdf"
        (args.output / name).write_bytes(raw)
        report.update(
            status="downloaded",
            file=name,
            matches_original=report["sha256"] == source["sha256"],
        )
    except Exception as exc:
        report.update(status="unavailable", error=str(exc))
    (args.output / "aip_http.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
