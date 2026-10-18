#!/usr/bin/env python3
"""Carga exclusivamente el archivo recibido; nunca vuelve a descargar datos."""
import argparse
import json
from pathlib import Path

from core.db import connect
from core.topology import load_infrastructure

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file",type=Path)
    args=parser.parse_args()
    with connect() as conn:
        print(json.dumps(load_infrastructure(conn,args.file)))
