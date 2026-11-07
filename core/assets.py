"""Resolve preserved logical source names to verified content-addressed blobs."""
import json
from pathlib import Path
from core.contracts import ROOT,sha256

def resolve_asset(path,expected_sha256=None):
    path=Path(path).resolve()
    if path.is_file():
        result=path
    else:
        if not path.is_relative_to(ROOT):raise FileNotFoundError(path)
        aliases=json.loads((ROOT/'config/asset_aliases.json').read_text(encoding='utf-8'))
        digest=aliases.get(path.relative_to(ROOT).as_posix())
        if not digest or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise FileNotFoundError(path)
        result=ROOT/'datos/entrada/blobs'/digest
        expected_sha256=expected_sha256 or digest
    if expected_sha256 and sha256(result)!=expected_sha256:raise ValueError('Original alterado: '+path.name)
    return result
