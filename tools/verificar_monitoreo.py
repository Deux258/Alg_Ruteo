"""Browser acceptance for the actual catalogue, automatic fire and coverage UI.

QA inventory: whole-area catalogue/sector selection, hide/show grid, start and
playback, fixed empirical probability, retained event on pause/seek, export,
coverage progress after landing. Exploratory: stale catalogue ID and rejected
probability override. Detection timing/resources are covered by unit fixtures.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from shapely.geometry import Point,shape
from shapely.ops import transform

from core.aerial_data import FWD
from tools.browser_ready import wait_patrol_ready


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8080',help='Usar localhost o HTTPS: la verificación de recursos 3D necesita Web Crypto')
    parser.add_argument('--chrome',help='Ejecutable Chromium del entorno QA, opcional')
    parser.add_argument('--output',default='evidencia/local/monitoreo_browser')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    checks={};errors=[]
    with sync_playwright() as p:
        options=dict(headless=True,args=['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        if args.chrome:options['executable_path']=args.chrome
        browser=p.chromium.launch(**options)
        page=browser.new_page(viewport=dict(width=1500,height=1000),accept_downloads=True)
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:print('POST',request.url,flush=True) if request.method=='POST' else None)
        page.on('response',lambda response:print('REPLY',response.status,response.url,flush=True) if response.request.method=='POST' else None)
        page.goto(args.url,wait_until='domcontentloaded');wait_patrol_ready(page)
        catalog=page.request.get(args.url+'/api/aereo/patrullaje/monitoreo').json()
        checks['whole_area_partition']=catalog['partition_complete'] and catalog['partition_gap_m2']<.01
        checks['catalogue_visible']=page.locator('#patrol-catalogue option').count()==len(catalog['sectors'])+1
        checks['fixed_baseline_visible']='CONAF' in page.locator('#fire-baseline').inner_text()
        checks['viewport_no_horizontal_clipping']=page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.locator('#show-sectors').uncheck();page.locator('#show-sectors').check()
        sector=min((s for s in catalog['sectors'] if s['area_m2']>20000),key=lambda s:transform(FWD,shape(s['target_polygon'])).representative_point().distance(Point(FWD(*s['origin']))))
        page.locator('#patrol-catalogue').select_option(sector['id'])
        checks['selection_has_target']=not page.locator('#calculate').is_disabled()
        page.screenshot(path=str(folder/'01_catalogo.png'))
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=360000) as flight:
            page.locator('#start-monitoring').click()
            page.wait_for_timeout(1000)
            print('Mission state:',page.locator('#message').inner_text(),'Errors:',errors,flush=True)
        if flight.value.status!=200:raise AssertionError(flight.value.text())
        simulation=flight.value.json()
        (folder/'simulation.json').write_text(json.dumps(simulation,ensure_ascii=False),encoding='utf-8')
        checks['automatic_without_manual_coordinates']=simulation['fire_event']['mode']=='automatic'
        checks['empirical_probability_not_amplified']=0<=simulation['fire_event']['probability']<.00001
        page.wait_for_function("!!document.querySelector('#player').dataset.phase && document.querySelector('#player').dataset.phase!=='idle'")
        page.locator('#pause').click();before=page.locator('#player').get_attribute('data-time')
        page.wait_for_timeout(150);checks['pause_keeps_clock']=before==page.locator('#player').get_attribute('data-time')
        checks['no_early_recovery_disclosure']=page.locator('#recovery-results').inner_text()==''
        page.locator('#finish-playback').click()
        checks['coverage_log_at_landing']='Cobertura acumulada del sector' in page.locator('#log').inner_text()
        checks['landed']=page.locator('#player').get_attribute('data-phase')=='landed'
        page.locator('#log').scroll_into_view_if_needed();page.screenshot(path=str(folder/'02_aterrizaje.png'))
        with page.expect_download() as download:page.locator('#export').click()
        download.value.save_as(str(folder/'mission.json'))
        bundle=json.loads((folder/'mission.json').read_text())
        checks['export_keeps_event']=bundle['simulation']['fire_event']['id']==simulation['fire_event']['id']
        bad=page.request.post(args.url+'/api/aereo/patrullaje',data=dict(patrol_id='stale',target_polygon=sector['target_polygon']))
        checks['stale_catalogue_rejected']=bad.status==422
        bad=page.request.post(args.url+'/api/aereo/patrullaje/simular',data=dict(sha256=simulation['result_sha256'],fire_probability_pct=100))
        checks['user_probability_rejected']=bad.status==422
        # Diagnostic manual event exercises the visible detection/recovery
        # controls without falsifying the empirical automatic occurrence rate.
        page.locator('#focus-target').click()
        page.get_by_text('Diagnóstico de detección manual',exact=True).click()
        page.locator('#fire').click();bounds=page.locator('#map').bounding_box()
        page.mouse.click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=180000) as detected:
            page.locator('#replay-nominal').click()
        diagnostic=detected.value.json()
        (folder/'diagnostic.json').write_text(json.dumps(diagnostic,ensure_ascii=False),encoding='utf-8')
        if detected.value.status!=200:raise AssertionError(detected.value.text())
        checks['diagnostic_detection']=diagnostic.get('detection') is not None
        checks['four_real_recovery_methods']=len(diagnostic.get('recovery',{}).get('recommendations',{}))==4
        page.wait_for_function("!document.querySelector('#finish-playback').disabled")
        page.locator('#finish-playback').click()
        checks['four_recovery_cards']=page.locator('#recovery-results .route-card').count()==4
        checks['shared_graph_visible']='Grafo compartido' in page.locator('#recovery-results').inner_text()
        page.locator('#recovery-results').scroll_into_view_if_needed();page.screenshot(path=str(folder/'03_recuperacion.png'))
        first=page.locator('#recovery-results input[type=checkbox]').first
        first.uncheck();first=page.locator('#recovery-results input[type=checkbox]').first;first.check()
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=180000) as branched:
            page.get_by_text('Reproducir desde la detección',exact=True).first.click()
        branch=branched.value.json()
        page.wait_for_function("!document.querySelector('#pause').disabled")
        page.locator('#pause').click()
        clock=float(page.locator('#player').get_attribute('data-time'))
        checks['alternative_starts_at_detection']=diagnostic['detection']['detected_at_s']<=clock<diagnostic['detection']['detected_at_s']+5
        checks['alternative_keeps_detection']=branch['detection']['detected_at_s']==diagnostic['detection']['detected_at_s'] and branch['detection']['fire_coordinates']==diagnostic['detection']['fire_coordinates']
        checks['chosen_technique_executed']=branch['recovery']['selected']['method']=='dijkstra_distance'
        page.locator('#view-toggle').click()
        page.wait_for_function("!document.querySelector('#terrain').hidden && !document.querySelector('#view-toggle').disabled",timeout=120000)
        checks['recovery_3d_visible']=page.locator('#terrain').is_visible()
        page.screenshot(path=str(folder/'04_recuperacion_3d.png'))
        checks['no_browser_errors']=not errors
        browser.close()
    report=dict(checks=checks,errors=errors,successful=all(checks.values()))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report));raise SystemExit(not report['successful'])


if __name__=='__main__':main()
