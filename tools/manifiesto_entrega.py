"""Hashes de una entrega revisable; nunca incluye .env, credenciales o directorios privados."""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--presentation", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    files = {}
    folders = [
        "core",
        "Infraestructura",
        "Metadata",
        "Amenazas",
        "BD",
        "config",
        "docker",
        "tests",
        "tools",
        "Sitio Web",
        "docs",
        "presentacion",
        "datos/entrada",
        str(args.evidence),
    ]
    for folder in folders:
        for p in sorted((root / folder).rglob("*")):
            if (
                p.is_file()
                and not any(
                    part in ["__pycache__", ".git", "node_modules"] for part in p.parts
                )
                and p.name != "manifest_entrega.json"
            ):
                files[p.relative_to(root).as_posix()] = hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
    for name in [
        "main",
        "README.md",
        "requirements.in",
        "requirements.lock",
        "requirements.aerial.lock",
        "compose.yaml",
        "compose.test.yaml",
        ".gitlab-ci.yml",
        ".gitattributes",
        ".gitignore",
        str(args.presentation),
    ]:
        p = root / name
        files[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    payload = dict(
        base_commit=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        local_changes=bool(
            subprocess.check_output(
                ["git", "status", "--porcelain", "--untracked-files=normal"],
                cwd=root,
                text=True,
            ).strip()
        ),
        files=files,
        external_delivery=dict(
            gitlab="pendiente de carga manual del equipo",
            canvas="pendiente de carga manual del equipo",
        ),
        warning="El commit de base no contiene los cambios locales; los hashes identifican la entrega. No incluye secretos ni datos/runs.",
    )
    payload["manifest_sha256"] = hashlib.sha256(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()
    path = root / args.evidence / "manifest_entrega.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(dict(files=len(files), manifest_sha256=payload["manifest_sha256"]))
    )


if __name__ == "__main__":
    main()
