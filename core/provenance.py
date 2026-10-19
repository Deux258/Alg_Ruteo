"""Huella del código y versiones efectivamente instaladas, sin leer secretos."""
import hashlib
import importlib.metadata
import os
import re
from core.contracts import ROOT,canonical,sha256


def software_manifest():
    files={}
    for folder in ['core','Infraestructura','Metadata','Amenazas','config','BD','tests','Sitio Web']:
        for p in sorted((ROOT/folder).rglob('*')):
            if p.is_file() and p.suffix in ['.py','.sql','.json','.html','.js','.css'] and 'vendor' not in p.parts:
                files[p.relative_to(ROOT).as_posix()]=sha256(p)
    for name in ['main','compose.yaml','compose.test.yaml','docker/Dockerfile.app','requirements.in','requirements.lock','requirements.aerial.lock','.gitlab-ci.yml']:
        files[name]=sha256(ROOT/name)
    installed={};mismatches=[]
    for name in ['requirements.lock','requirements.aerial.lock']:
        for line in (ROOT/name).read_text().splitlines():
            match=re.match(r'^([A-Za-z0-9_-]+)==([^ ]+)',line)
            if not match:continue
            package,version=match.groups()
            try:actual=importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:actual=None
            installed[package]=actual
            if actual!=version:mismatches.append(dict(package=package,locked=version,installed=actual))
    return dict(commit=os.getenv('BUILD_COMMIT',os.getenv('CI_COMMIT_SHA','unknown')),code_sha256=hashlib.sha256(canonical(files)).hexdigest(),files=files,installed=installed,lock_mismatches=mismatches)
