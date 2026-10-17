import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.contracts import ROOT


class MainCLI(unittest.TestCase):
    def test_help_needs_no_docker(self):
        r=subprocess.run(['bash',str(ROOT/'main'),'--help'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0);self.assertIn('iniciar',r.stdout)

    def test_shell_syntax(self):
        self.assertEqual(subprocess.run(['bash','-n',str(ROOT/'main')]).returncode,0)

    def test_preflight_failure_stops_before_starting_database_or_web(self):
        # Doble de CLI: comprueba el control de flujo, no acredita ejecución Docker.
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);shutil.copy2(ROOT/'main',p/'main')
            (p/'.env').write_text('POSTGRES_PASSWORD=test-only\nWEB_DB_PASSWORD=test-only\n')
            trace=p/'calls.jsonl';fake=p/'docker'
            fake.write_text(f'#!{sys.executable}\nimport sys,json\nwith open({str(trace)!r},"a") as f:f.write(json.dumps(sys.argv[1:])+"\\n")\nraise SystemExit(42 if "preflight" in sys.argv else 0)\n')
            fake.chmod(0o755)
            env=os.environ.copy();env['PATH']=str(p)+os.pathsep+env['PATH']
            result=subprocess.run(['bash',str(p/'main'),'iniciar','--scope','completo'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,42)
            calls=[json.loads(x) for x in trace.read_text().splitlines()]
            self.assertTrue(any('preflight' in c for c in calls))
            self.assertFalse(any('up' in c for c in calls))

if __name__=='__main__':unittest.main()
