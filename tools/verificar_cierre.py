"""Acceptance of compact transport, blocked diagnostics and delayed UI responses. No video."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, Error as BrowserError
from shapely.geometry import shape
from shapely import prepare
from shapely.ops import transform
from core.aerial_data import FWD
from core.communes import commune_index


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:18083')
    parser.add_argument('--chrome',required=True)
    parser.add_argument('--output',default='evidencia/local/cierre')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    checks={};errors=[];sizes={};root=args.url.rstrip('/')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chrome,headless=True,args=['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        context=browser.new_context(viewport={'width':1500,'height':1000},accept_downloads=True)
        request=context.request
        initial=request.get(root+'/api/aereo/patrullaje/mapa?view=summary',timeout=300000)
        if initial.status!=200:raise AssertionError(initial.text())
        model=initial.json();sizes['map_summary']=len(initial.body());checks['initial_under_1MiB']=sizes['map_summary']<=1048576
        checks['shared_weather_declared']=all(k in model['global_layers'] for k in ('M4','A1'))
        ref=model['resources']['terrain'];resource=request.get(root+ref['url']);etag=resource.headers.get('etag')
        checks['immutable_etag']=bool(etag) and 'immutable' in resource.headers.get('cache-control','')
        checks['resource_304']=request.get(root+ref['url'],headers={'If-None-Match':etag}).status==304
        checks['dynamic_no_store']=initial.headers.get('cache-control')=='no-store'
        base=dict(target_polygon=model['demo_polygon'],origin=model['default_origin'],time=model['validation']['default_time'],station_ids=[],scenarios=1000)
        battery=request.post(root+'/api/aereo/patrullaje?view=summary',data=dict(base,preferences={'battery_budget_s':60}),timeout=300000)
        if battery.status!=200:raise AssertionError(battery.text())
        low=battery.json()
        checks['60s_rejected_without_fictional_route']=low['status']=='blocked' and all(not r['coordinates'] and r['status']=='blocked' for r in low['routes'].values())
        blocked=next(w for w in model['weather'] if max(w['wind_speed_ms'],w['wind_gust_ms'])>=model['profile']['wind_limit_ms'])
        weather=request.post(root+'/api/aereo/patrullaje?view=summary',data=dict(base,time=blocked['valid_at']),timeout=300000)
        if weather.status!=200:raise AssertionError(weather.text())
        diagnosis=weather.json();sizes['blocked_summary']=len(weather.body())
        probs=request.get(root+diagnosis['resources']['probabilidades']['url']).json()
        checks['blocked_A1_exportable']=diagnosis['status']=='blocked' and bool(probs['nodes']) and all(n['by_threat']['A1:weather']==100 and n['probability_pct']==100 for n in probs['nodes'])
        checks['blocked_routes_empty']=len(diagnosis['routes'])==4 and all(not row['coordinates'] for row in diagnosis['routes'].values())
        write=lambda name,value:(folder/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        write('blocked_diagnostic.json',diagnosis)
        index=commune_index()
        for cut in ('05101','05109'):
            filtered=request.get(root+'/api/aereo/patrullaje/mapa?view=summary&commune_id='+cut,timeout=300000)
            if filtered.status!=200:raise AssertionError(filtered.text())
            summary=filtered.json();sizes['commune_'+cut]=len(filtered.body());polygon=index.metric(cut).buffer(.03);prepare(polygon)
            checks['all_layers_spatially_clipped_'+cut]=True
            for key,ref in summary['resources']['layers'].items():
                fc=request.get(root+ref['url'],timeout=120000).json()
                checks['all_layers_spatially_clipped_'+cut]&=all(polygon.covers(transform(FWD,shape(f['geometry']))) for f in fc['features'])
            rendered=request.get(root+summary['resources']['render']['url'],timeout=120000).json()
            checks['terrain_and_objects_filtered_'+cut]='terrain' in rendered['typed_assets']['groups'] and rendered['commune_id']==cut
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        from tools.browser_ready import wait_patrol_ready
        page.goto(root,wait_until='domcontentloaded');wait_patrol_ready(page)
        page.wait_for_function("document.querySelector('#geography-status').getAttribute('aria-busy')==='false'",timeout=300000)
        page.locator('#demo').click()
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/patrullaje') and r.request.method=='POST',timeout=360000) as pending:page.locator('#calculate').click()
        summary=pending.value.json();sizes['mission_summary']=len(pending.value.body())
        page.wait_for_function("!document.querySelector('#export').disabled",timeout=120000)
        checks['mission_under_1MiB']=sizes['mission_summary']<=1048576
        checks['budgets_separated']=summary['effective_profile']['battery_budget_s']==1200 and summary['planning_profile']['battery_budget_s']==1140
        page.locator('#route-mode').select_option('comparison')
        checks['explicit_resilience_result']='resiliencia' in page.locator('#resilience-summary').inner_text().lower() or 'Empate entre las cuatro técnicas' in page.locator('#resilience-summary').inner_text()
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=120000) as flight:page.locator('#play').click()
        nominal=flight.value.json();page.locator('#pause').click()
        held=[]
        def hold(route):held.append(route)
        def wait_held(rows):
            for _ in range(200):
                if rows:return
                page.wait_for_timeout(50)
            raise AssertionError('La solicitud retrasada no llegó')
        def release(route,value):
            try:route.fulfill(status=200,json=value)
            except BrowserError:pass # A cancelled browser request cannot consume its obsolete response.
        page.route('**/simular',hold)
        page.get_by_text('Diagnóstico de detección manual',exact=True).click()
        page.locator('#fire').click();bounds=page.locator('#map').bounding_box();page.mouse.click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
        page.locator('#simulate').click();page.wait_for_function("document.querySelector('#simulate').disabled")
        wait_held(held)
        page.locator('#clear-fire').click()
        for route in held:release(route,nominal)
        page.wait_for_timeout(250)
        checks['stale_focus_simulation_ignored']=page.locator('#log').inner_text()=='' and page.locator('#pause').is_disabled()
        page.unroute('**/simular',hold)
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=120000):page.locator('#play').click()
        page.locator('#pause').click()
        resources=[]
        def hold_asset(route):
            response=route.fetch(timeout=120000);resources.append((route,response))
        page.route('**/recursos/*',hold_asset)
        page.locator('#drone-view').click()
        page.wait_for_function("document.querySelector('#view-toggle').disabled",timeout=30000)
        wait_held(resources)
        options=page.locator('#chosen option').evaluate_all('(rows)=>rows.map(r=>r.value)')
        selected=page.locator('#chosen').input_value();page.locator('#chosen').select_option(next(v for v in options if v!=selected))
        for route,response in resources:
            try:route.fulfill(response=response)
            except BrowserError:pass
        page.unroute('**/recursos/*',hold_asset);page.wait_for_timeout(500)
        checks['flight_change_during_camera_safe']=page.locator('#drone-view').get_attribute('aria-pressed')=='false' and page.locator('#fpv-hud').is_hidden()
        if page.locator('#terrain').is_visible():page.locator('#view-toggle').click()
        held.clear();page.route('**/patrullaje?view=summary',hold)
        page.locator('#calculate').click();page.wait_for_function("document.querySelector('#calculate').disabled")
        wait_held(held)
        page.locator('#seed').fill('20261106');page.locator('#seed').dispatch_event('change')
        for route in held:release(route,summary)
        page.wait_for_timeout(300)
        checks['seed_change_invalidates_old_mission']=page.locator('.route-card').count()==0 and page.locator('#export').is_disabled()
        page.unroute('**/patrullaje?view=summary',hold)
        page.screenshot(path=str(folder/'cierre_interfaz.png'),full_page=True)
        context.close();browser.close()
    report=dict(checks=checks,browser_errors=errors,sizes_bytes=sizes,successful=all(checks.values()) and not errors,video=None)
    (folder/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    if not report['successful']:raise SystemExit(1)


if __name__=='__main__':main()
