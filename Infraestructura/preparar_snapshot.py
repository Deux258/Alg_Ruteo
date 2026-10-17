#!/usr/bin/env python3
"""Reconstruye infraestructura desde originales conservados; red vial o malla legada."""
import argparse
import json
from pathlib import Path

from core.contracts import ROOT, prepare_snapshot, write_json

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--mode",choices=['snapshot','online'],default='snapshot')
    args=parser.parse_args()
    cfg=json.loads((ROOT/"config/proyecto.json").read_text())
    doc=prepare_snapshot(cfg,args.run_id,args.mode)
    path=args.output or ROOT/"datos/runs"/doc["run_id"]/"infraestructura.json"
    write_json(path,doc)
    print(json.dumps({"run_id":doc["run_id"],"path":str(path),"nodes":len(doc["nodes"]),"edges":len(doc["edges"])}))
