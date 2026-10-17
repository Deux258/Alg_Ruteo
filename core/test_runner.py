"""Ejecuta la suite y conserva un resultado revisable, sin ocultar omisiones."""
import contextlib
import json
import platform
import time
import unittest
from datetime import datetime,timezone

from core.contracts import ROOT,write_json


def main():
    folder=ROOT/'evidencia/local';folder.mkdir(parents=True,exist_ok=True)
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),top_level_dir=str(ROOT))
    start=time.monotonic()
    with (folder/'pruebas.log').open('w') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    report={'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'tests_run':result.testsRun,
            'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
            'successful':result.wasSuccessful(),'duration_s':round(time.monotonic()-start,3),
            'python':platform.python_version(),'omitted':[reason for _,reason in result.skipped]}
    try:
        from core.db import connect
        with connect() as conn:
            report['database_versions']=conn.execute('SELECT version() AS postgres,postgis_full_version() AS postgis,pgr_version() AS pgrouting').fetchone()
    except Exception:
        report['database_versions']=None
    write_json(folder/'pruebas.json',report)
    print(json.dumps(report,ensure_ascii=False))
    return 0 if result.wasSuccessful() else 1


if __name__=='__main__':raise SystemExit(main())
