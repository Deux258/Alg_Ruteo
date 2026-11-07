"""Full regression and browser acceptance, exclusively on the disposable DB."""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from core.contracts import ROOT, write_json


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser-only',action='store_true',help='Debug browser/transport stages separately; does not certify Python regression')
    args=parser.parse_args()
    # Hard guard: neither a reused production DSN nor a production host is acceptable.
    if os.getenv('DB_HOST') != 'dbtest' or os.getenv('DB_NAME') != 'ruteo_test' or os.getenv('DATABASE_URL'):
        raise RuntimeError('QA requiere dbtest/ruteo_test, sin DATABASE_URL')
    folder = ROOT/'evidencia/local'; folder.mkdir(parents=True, exist_ok=True)
    from core.provenance import software_manifest
    report = dict(video=None, database='disposable:dbtest/ruteo_test', stages=[],
                  scope='browser' if args.browser_only else 'full', python_included=not args.browser_only,
                  successful=False,status='running',source_code_sha256=software_manifest()['code_sha256'])
    report_path=folder/('acceptance_browser.json' if args.browser_only else 'acceptance.json')
    write_json(report_path, report)

    def execute(name, command):
        start = time.monotonic()
        with (folder/(name+'.log')).open('w', encoding='utf-8') as log:
            result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
        report['stages'].append(dict(name=name, returncode=result.returncode, duration_s=round(time.monotonic()-start, 3)))
        if result.returncode:report['status']='failed'
        write_json(report_path, report)
        if result.returncode:
            print((folder/(name+'.log')).read_text(encoding='utf-8')[-12000:])
            raise RuntimeError('Falló '+name)

    if not args.browser_only:
        execute('python', [sys.executable, '-m', 'core.test_runner'])
        python_report = json.loads((folder/'pruebas.json').read_text())
        if python_report['skipped']:
            raise RuntimeError('La suite de entrega no permite omitir pruebas')
    execute('node', ['node', '--test', *map(str, sorted((ROOT/'tests').glob('*.mjs')))])

    # Tests also publish road fixtures. Restore the complete aerial publication only
    # inside this disposable database before starting the actual HTTP service.
    from core.pipeline import run
    from core.db import connect
    result = run('completo', 'snapshot')
    with connect() as conn:
        conn.execute("SELECT routing.publish_run(%s,'completo')", (result['run_id'],))
    execute('prepare_scene', [sys.executable, '-m', 'tools.preparar_escena'])
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        chrome = p.chromium.executable_path
    execute('verificar_estados_ui', [sys.executable, '-m', 'tools.verificar_estados_ui', '--chrome', chrome,
                                   '--output', str(folder/'verificar_estados_ui')])
    env = dict(os.environ, PORT='18086', DB_USER='routing_web',
               DB_PASSWORD=os.environ['WEB_DB_PASSWORD'])
    with (folder/'web.log').open('w', encoding='utf-8') as log:
        server = subprocess.Popen([sys.executable, '-m', 'core.web'], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            root = 'http://127.0.0.1:18086'
            for _ in range(120):
                if server.poll() is not None: raise RuntimeError('Servidor QA terminado')
                try:
                    with urllib.request.urlopen(root+'/health', timeout=2) as response:
                        if response.status == 200: break
                except OSError: time.sleep(.5)
            else: raise RuntimeError('Servidor QA no disponible')
            for tool in ('verificar_patrullaje', 'verificar_recarga', 'verificar_entorno', 'verificar_reproductor', 'verificar_cierre'):
                execute(tool, [sys.executable, '-m', 'tools.'+tool, '--url', root, '--chrome', chrome,
                               '--output', str(folder/tool)])
        finally:
            server.terminate()
            try: server.wait(timeout=10)
            except subprocess.TimeoutExpired: server.kill(); server.wait()
    execute('benchmark', [sys.executable, '-m', 'tools.benchmark_patrol', '--output', str(folder/'benchmark.json')])
    report['software'] = software_manifest()
    if report['software']['code_sha256']!=report['source_code_sha256']:
        raise RuntimeError('El código cambió durante la validación; repetir con una versión congelada')
    report['successful'] = True;report['status']='passed'
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__': main()
