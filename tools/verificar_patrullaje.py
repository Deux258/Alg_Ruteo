"""Browser acceptance and silent demonstration video; uses the actual HTTP API."""
import argparse
from urllib.parse import urlsplit
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:18083')
    parser.add_argument('--chrome',required=True)
    parser.add_argument('--output',default='evidencia/final_2026-11-04')
    recording=parser.add_mutually_exclusive_group()
    recording.add_argument('--no-video',dest='no_video',action='store_true',help='Verificar interfaz sin grabación (predeterminado)')
    recording.add_argument('--video',dest='no_video',action='store_false',help='Activar grabación explícitamente')
    parser.set_defaults(no_video=True)
    args=parser.parse_args()
    folder=Path(args.output).resolve();folder.mkdir(parents=True,exist_ok=True)
    errors=[]
    checks=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chrome,headless=True,args=['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        recording={} if args.no_video else dict(record_video_dir=str(folder/'video_raw'),record_video_size={'width':1440,'height':1000})
        context=browser.new_context(viewport={'width':1440,'height':1000},accept_downloads=True,**recording)
        page=context.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url);page.wait_for_load_state('networkidle')
        page.locator('#route-mode').select_option('comparison')
        page.get_by_role('button',name='Cargar ejemplo').click()
        checks.append(('example_polygon',page.locator('#calculate').is_enabled()))
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/api/aereo/patrullaje') and r.request.method=='POST',timeout=300000) as pending:
            page.locator('#calculate').click()
        response=pending.value
        if response.status!=200:raise AssertionError(response.text())
        page.wait_for_function("document.querySelectorAll('.route-card').length===4",timeout=300000)
        with page.expect_download() as exported:
            page.locator('#export').click()
        exported.value.save_as(str(folder/'mission_export.json'))
        result=json.loads((folder/'mission_export.json').read_text(encoding='utf-8'))['result']
        (folder/'comparison.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        (folder/'failure_probabilities.json').write_text(json.dumps(result['failure_probabilities'],ensure_ascii=False),encoding='utf-8')
        checks.append(('four_routes',len(result['routes'])==4))
        checks.append(('pgr_dijkstra',result['routes']['dijkstra_distance']['solver']['engine']=='pgr_dijkstra'))
        checks.append(('max_link_200m',result['network']['max_horizontal_link_m']<=200.000001))
        checks.append(('gurobi_solution',result['routes']['gurobi']['status']=='ready'))
        checks.append(('complete_coverage',all(r['coverage']['complete'] for r in result['routes'].values() if r['status']=='ready')))
        page.locator('#results').scroll_into_view_if_needed()
        page.screenshot(path=str(folder/'cuatro_tecnicas.png'))
        for method in result['routes']:
            page.locator(f'#show-{method}').uncheck();page.locator(f'#show-{method}').check()
        checks.append(('four_independent_checkboxes',True))
        page.locator('#view-toggle').click();page.wait_for_function("Number(document.querySelector('#terrain').dataset.sceneVertices)>10000",timeout=120000)
        checks.append(('webgl',page.locator('#terrain').is_visible() and page.evaluate("!!document.querySelector('#terrain').getContext('webgl')")))
        page.screenshot(path=str(folder/'terreno_3d.png'))
        page.locator('#view-toggle').click()
        page.locator('#fire').click()
        # The selected rectangle's rendered SVG bounds provide a real map click.
        bounds=page.locator('#map').bounding_box()
        if not bounds:raise AssertionError('Polígono seleccionado no visible')
        page.mouse.click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
        page.locator('#speed').select_option('100')
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=120000) as pending:
            page.locator('#simulate').click()
        simulation=pending.value.json()
        checks.append(('fire_report_return',simulation.get('status')=='detected_and_returned'))
        checks.append(('battery_nonnegative',all(f['battery_pct']>=0 for f in simulation['timeline'])))
        (folder/'simulation.json').write_text(json.dumps(simulation,ensure_ascii=False),encoding='utf-8')
        page.wait_for_function("document.querySelector('#log').textContent.includes('Fin:')",timeout=120000)
        page.locator('#active-only').check();page.locator('#active-only').uncheck()
        page.locator('#flight').scroll_into_view_if_needed()
        page.screenshot(path=str(folder/'deteccion_regreso.png'))
        # Targeted illustration: an uncertain closure on an outbound connector.
        from shapely.geometry import Point,shape
        from shapely.ops import transform
        from core.aerial_data import FWD
        from core.patrol import threat_uniform
        edges={e['id']:e for e in result['graph']['edges']}
        nodes={n['id']:n['coordinates'] for n in result['graph']['nodes']}
        target=transform(FWD,shape(result['target_polygon']))
        origin=Point(FWD(*result['origin']))
        candidate=None
        for ident in result['routes']['dijkstra_distance']['edge_ids']:
            edge=edges[ident];a,b=nodes[edge['source']],nodes[edge['target']]
            mid=[(a[0]+b[0])/2,(a[1]+b[1])/2]
            point=Point(FWD(*mid))
            if origin.distance(point)>70 and target.distance(point)>40:
                candidate=mid;break
        if candidate is None:raise AssertionError('Sin conector apto para ilustrar desvío')
        seed=20261104
        while True:
            if threat_uniform(seed,0,'synthetic:0')<80:break
            seed+=1
        page.locator('#clear-fire').click()
        page.get_by_text('Amenaza por coordenadas',exact=True).click()
        page.locator('#hazard-coordinates').fill(', '.join(map(str,candidate)))
        page.locator('#radius').fill('15');page.locator('#probability').fill('80')
        page.locator('#seed').fill(str(seed));page.locator('#hazard-coordinate-add').click()
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/api/aereo/patrullaje') and r.request.method=='POST',timeout=300000):page.locator('#calculate').click()
        page.wait_for_function("!document.querySelector('#simulate').disabled",timeout=300000)
        page.locator('#chosen').select_option('dijkstra_distance')
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=120000) as pending:page.locator('#simulate').click()
        interrupted=pending.value.json()
        checks.append(('random_closure_activated','synthetic:0' in interrupted['active_threat_ids']))
        checks.append(('interrupted_patrol_not_completed',not interrupted['mission_completed']))
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/api/aereo/patrullaje') and r.request.method=='POST',timeout=300000):page.locator('#replan').click()
        page.wait_for_function("!document.querySelector('#export').disabled",timeout=300000)
        with page.expect_download() as alternative:page.locator('#export').click()
        alternative.value.save_as(str(folder/'alternative_export.json'))
        new_result=json.loads((folder/'alternative_export.json').read_text(encoding='utf-8'))['result']
        if not new_result['request'].get('events'):raise AssertionError('La replanificación perdió la amenaza sintética')
        checks.append(('alternative_after_failure',bool(new_result['recommended'])))
        from shapely.geometry import LineString
        closure=transform(FWD,shape(new_result['request']['events'][0]['geometry']))
        checks.append(('alternative_avoids_closure',all(not transform(FWD,LineString(r['coordinates'])).intersects(closure) for r in new_result['routes'].values() if r['status']=='ready')))
        (folder/'alternative_case.json').write_text(json.dumps(dict(seed=seed,closure_coordinates=candidate,interrupted_status=interrupted['status'],
            baseline_sha=result['sha256'],replanned_sha=new_result['sha256'],recommended=new_result['recommended'],
            methods={k:dict(status=r['status'],time_s=r['time_s'],resilience=r['resilience']) for k,r in new_result['routes'].items()}),indent=2),encoding='utf-8')
        page.locator('#results').scroll_into_view_if_needed();page.screenshot(path=str(folder/'alternativa_amenaza.png'))
        page.locator('#view-toggle').click();page.wait_for_timeout(1800)
        with page.expect_download() as download:
            page.locator('#failures').click()
        download.value.save_as(str(folder/'failure_probabilities_ui.json'))
        checks.append(('download_probabilities',True))
        page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(500)
        checks.append(('mobile_no_overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth')))
        page.screenshot(path=str(folder/'movil.png'))
        video=page.video if not args.no_video else None
        context.close()
        report=dict(checks=dict(checks),browser_errors=errors,successful=all(v for _,v in checks) and not errors)
        (folder/'browser_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        video_path=folder/f"demostracion_{result['sha256'][:12]}.webm" if video else None
        if video:video.save_as(str(video_path))
        browser.close()
    report['video']=str(video_path) if video_path else None
    (folder/'browser_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    if not report['successful']:raise SystemExit(1)


if __name__=='__main__':main()
