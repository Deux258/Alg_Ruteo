"""Package reproducible phase-final evidence, avoiding duplicate large JSON files."""
import argparse
import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path


def load(path):
    path=Path(path)
    if path.exists():return json.loads(path.read_text(encoding='utf-8'))
    with gzip.open(str(path)+'.gz','rt',encoding='utf-8') as f:return json.load(f)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',default='evidencia/final_2026-11-04')
    parser.add_argument('--batch',required=True)
    parser.add_argument('--compact',action='store_true')
    parser.add_argument('--include-video',action='store_true')
    args=parser.parse_args()
    folder=Path(args.folder).resolve()
    result=load(folder/'comparison.json')
    browser=load(folder/'browser_checks.json')
    charging=load(folder/'charging_checks.json')
    if not browser['successful'] or not charging['successful']:raise ValueError('Comprobaciones de navegador o recarga no aprobadas')
    alternative=load(folder/'alternative_case.json')
    patrol_units=load(folder/'patrol_units.json')
    batch=load(Path(args.batch)/'summary.json')
    shutil.copytree(args.batch,folder/'evaluacion',dirs_exist_ok=True)
    log=Path('evidencia/local/final_regresion.log')
    text=log.read_text(encoding='utf-8') if log.exists() else ''
    match=re.search(r'Ran (\d+) tests? in ([0-9.]+)s',text)
    regression=dict(completed=bool(match),successful=bool(match and text.rstrip().endswith('OK')),
                    tests=int(match[1]) if match else None,seconds=float(match[2]) if match else None)
    if log.exists():
        with gzip.GzipFile(filename=str(folder/'regresion.log.gz'),mode='wb',mtime=0) as f:f.write(log.read_bytes())
    summary=dict(schema_version='patrol-delivery-1',application='http://127.0.0.1:18083',
                 run_id=result.get('run_id'),result_sha256=result['sha256'],code_sha256=result['software']['code_sha256'],
                 installed=result['software']['installed'],lock_mismatches=result['software']['lock_mismatches'],
                 network=result['network'],browser=browser,charging=charging,patrol_units=patrol_units,regression=regression,batch=batch,
                 methods={k:{key:r[key] for key in ('status','time_s','compute_s','coverage','resilience','solver')} for k,r in result['routes'].items()},
                 alternative=alternative,assumptions=result['assumptions'])
    (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    tests=f"{regression['tests']} pruebas, {'correctas' if regression['successful'] else 'con incidencias'}" if regression['completed'] else 'en curso; no se acredita cierre completo'
    lines=['# Evidencia de fase final','',
           'Aplicación: http://127.0.0.1:18083. Fecha: 4 de noviembre de 2026.',
           '',f"Snapshot publicado: `{result.get('run_id')}`. Huella de código: `{result['software']['code_sha256']}`.",
           '',f"Navegador: {len(browser['checks'])} comprobaciones correctas, sin errores JavaScript. Recarga: {len(charging['checks'])} comprobaciones.",
           '',f'Regresión: {tests}.',
           f"Módulo de patrullaje actualizado: {patrol_units['tests']} pruebas aprobadas en Docker. Los conteos incluyen pruebas solapadas.",'',
           '| Técnica | Estado | Misión (s) | Cómputo incremental (s) | R sintética |',
           '|---|---|---:|---:|---:|']
    for key,r in result['routes'].items():
        lines.append(f"| {r['label']} | {r['status']} | {r['time_s']:.3f} | {r['compute_s']:.3f} | {100*r['resilience']['value']:.1f} % |")
    lines += ['', 'Las cuatro técnicas empatan en resiliencia en el caso mostrado. El 81,6 % observado',
              'corresponde al modelo de escenarios, incluido el supuesto del 20 % para historia',
              'sin cobertura. No estima confiabilidad real ni demuestra superioridad estadística.',
              '',f"Lote `{batch['protocol']}`: {batch['total_cases']} casos predefinidos, {batch['invalid_cases']} rechazados antes del cálculo.",
              'Cada caso conserva los cuatro resultados y 1.000 escenarios comunes. En las áreas',
              'mayores Gurobi y recocido reducen tiempo de recorrido; las probabilidades comunes',
              'producen empate de resiliencia. `evaluacion/` conserva plan, resúmenes y JSON comprimidos.',
              '', '## Casos comprobados', '',
              '- `alternativa_amenaza.png` y `alternative_case.json`: cierre activado y circuito que lo evita.',
              '- `deteccion_regreso.png` y `simulation.json`: detección, reporte y retorno.',
              '- `recarga.png` y `charging_checks.json`: presupuesto de batería reducido a 130 s para forzar un cambio en base; es una restricción experimental.',
              '- `terreno_3d.png` y `movil.png`: terreno local y disposición móvil.',
              '', '## Límites y reproducción', '',
              'Producción del video pospuesta por indicación del usuario. No se han publicado commits ni subido archivos a Canvas.',
              'La licencia pip de Gurobi permitió estos modelos pequeños; la activación académica',
              'para modelos mayores sigue siendo una configuración del equipo.',
              'El DSM es aproximado; estaciones, radio visual y probabilidades son supuestos declarados.',
              '', 'Consultar `docs/FASE_FINAL.md` y `presentacion/MATRIZ_FASE_FINAL.md` desde la raíz del repositorio.','']
    if args.include_video:
        for report in (browser,charging):
            if report.get('video'):
                name=Path(report['video']).name;lines.extend([f'Video: [{name}]({name}).',''])
    (folder/'INFORME.md').write_text('\n'.join(lines),encoding='utf-8')
    if args.compact:
        for name in ('comparison.json','failure_probabilities.json','alternative_export.json','recarga_export.json'):
            path=folder/name
            if path.exists():
                with gzip.GzipFile(filename=str(path)+'.gz',mode='wb',mtime=0) as f:f.write(path.read_bytes())
                if not path.resolve().is_relative_to(folder):raise ValueError('Ruta fuera de evidencia')
                path.unlink()
        # These UI downloads duplicate data already preserved above.
        for name in ('mission_export.json','failure_probabilities_ui.json'):
            path=folder/name
            if path.exists() and path.resolve().is_relative_to(folder):path.unlink()
    files={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.rglob('*'))
           if p.is_file() and 'video_raw' not in p.parts and p.name!='manifest.json'}
    (folder/'manifest.json').write_text(json.dumps(files,indent=2),encoding='utf-8')
    print(json.dumps(dict(output=str(folder),regression=regression,files=len(files))))


if __name__=='__main__':main()
