"""Acceptance of real local geographic layers and WebGL rendering; no video."""
import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:18083')
    parser.add_argument('--chrome',required=True)
    parser.add_argument('--output',default='evidencia/entorno_3d_2026-11-04')
    parser.add_argument('--mission',action='store_true')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    checks={};errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chrome,headless=True,args=['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        context=browser.new_context(viewport={'width':1500,'height':1000},accept_downloads=True)
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        with page.expect_response(lambda r:r.url.endswith('/patrullaje/mapa'),timeout=240000) as pending:page.goto(args.url)
        response=pending.value
        if response.status!=200:raise AssertionError(response.text())
        page.wait_for_selector('#geo-buildings',timeout=120000);page.wait_for_load_state('networkidle',timeout=120000)
        # APIRequestContext bypasses Chrome's small DevTools response-body cache.
        model=context.request.get(args.url+'/api/aereo/patrullaje/mapa',timeout=120000).json();geo=model['geography']
        checks['six_real_geographic_layers']=all(geo['counts'].get(k,0)>0 for k in ('buildings','water','landcover','trees','roads','contours'))
        checks['source_sha_and_license']=len(geo['source']['sha256'])==64 and geo['source']['license']=='ODbL 1.0'
        checks['osm_base_and_credit']=page.locator('.leaflet-tile-pane img').count()>0 and 'OpenStreetMap' in page.locator('.leaflet-control-attribution').inner_text()
        checks['osm_tiles_loaded']=page.locator('.leaflet-tile-pane img').evaluate_all('(imgs)=>imgs.some(i=>i.complete&&i.naturalWidth>0)')
        page.get_by_text('Fuentes, alturas y cobertura',exact=True).click()
        checks['height_estimates_disclosed']=geo['height_estimates']>0 and 'estimad' in page.locator('#geography-source').inner_text()
        page.get_by_text('Fuentes, alturas y cobertura',exact=True).click()
        page.screenshot(path=str(folder/'openstreetmap_capas.png'))
        page.locator('#base-style').select_option('local');page.wait_for_timeout(700)
        checks['offline_local_base']=page.locator('.leaflet-tile-pane img').count()==0 and 'local activa' in page.locator('#tile-status').inner_text()
        page.screenshot(path=str(folder/'cartografia_local.png'))
        page.locator('#view-toggle').click();page.wait_for_function("Number(document.querySelector('#terrain').dataset.sceneVertices)>10000",timeout=120000)
        canvas=page.locator('#terrain')
        checks['webgl_geometry']=canvas.is_visible() and int(canvas.get_attribute('data-scene-vertices') or 0)>10000
        checks['webgl_no_error']=page.evaluate("document.querySelector('#terrain').getContext('webgl').getError()===0")
        initial=canvas.screenshot()
        checks['independent_3d_layers']=True
        for key in ('buildings','water','landcover','trees','roads','contours'):
            page.locator(f'#geo-{key}').uncheck()
            checks['independent_3d_layers'] &= key not in (canvas.get_attribute('data-scene-layers') or '').split(',')
            page.locator(f'#geo-{key}').check()
        page.locator('#terrain-reset').click();page.screenshot(path=str(folder/'entorno_3d_general.png'))
        bounds=canvas.bounding_box();page.mouse.move(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2);page.mouse.wheel(0,-1000);page.wait_for_timeout(300)
        checks['zoom_changes_render']=hashlib.sha256(initial).hexdigest()!=hashlib.sha256(canvas.screenshot()).hexdigest()
        page.screenshot(path=str(folder/'entorno_3d_detalle.png'))
        page.locator('#terrain-reset').click()
        if args.mission:
            page.locator('#demo').click()
            with page.expect_response(lambda r:r.url.endswith('/api/aereo/patrullaje') and r.request.method=='POST',timeout=300000) as computed:page.locator('#calculate').click()
            if computed.value.status!=200:raise AssertionError(computed.value.text())
            page.wait_for_selector('.route-card',timeout=30000)
            with page.expect_download() as mission:page.locator('#export').click()
            mission.value.save_as(str(folder/'mission.json'))
            result=json.loads((folder/'mission.json').read_text(encoding='utf-8'))['result']
            checks['four_terrain_aware_routes']=all(r['status']=='ready' for r in result['routes'].values())
            checks['same_obstacle_snapshot']=result['geographic_scene']['sha256']==geo['sha256']
            checks['links_up_to_200m']=result['network']['max_horizontal_link_m']<=200.00001
            page.wait_for_selector('.route-card',timeout=30000);page.locator('#terrain-mission').click();page.screenshot(path=str(folder/'mision_3d.png'))
            (folder/'mission_summary.json').write_text(json.dumps(dict(geographic_scene=result['geographic_scene'],network=result['network'],routes={k:dict(status=r['status'],time_s=r['time_s'],coverage=r['coverage']) for k,r in result['routes'].items()}),indent=2),encoding='utf-8')
        page.locator('#view-toggle').click();page.locator('#base-style').select_option('osm')
        checks['osm_returns_after_3d']=page.locator('.leaflet-tile-pane img').count()>0
        page.get_by_text('Fuentes, alturas y cobertura',exact=True).click()
        with page.expect_download() as download:page.locator('#export-geography').click()
        download.value.save_as(str(folder/'entorno.geojson'))
        exported=json.loads((folder/'entorno.geojson').read_text(encoding='utf-8'))
        checks['export_all_layers']=len(exported['features'])==sum(geo['counts'].values())
        page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(600)
        checks['mobile_no_overflow']=page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
        page.screenshot(path=str(folder/'movil.png'))
        context.close();browser.close()
    report=dict(checks=checks,counts=geo['counts'],height_estimates=geo['height_estimates'],
                woodland_symbols=geo['woodland_symbols'],source=geo['source'],scene_sha256=geo['sha256'],
                errors=errors,video=None,successful=all(checks.values()) and not errors)
    (folder/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(successful=report['successful'],checks=checks,errors=errors)))
    if not report['successful']:raise SystemExit(1)


if __name__=='__main__':main()
