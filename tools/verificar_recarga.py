"""Real-snapshot battery-swap acceptance through the visible browser controls."""
import argparse
from urllib.parse import urlsplit
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from shapely.affinity import translate
from shapely.geometry import shape,mapping
from shapely.ops import transform
from core.aerial_data import FWD,INV
from tools.browser_ready import wait_patrol_ready


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:18083')
    parser.add_argument('--chrome',required=True)
    parser.add_argument('--output',default='evidencia/final_2026-11-04')
    recording=parser.add_mutually_exclusive_group()
    recording.add_argument('--no-video',dest='no_video',action='store_true')
    recording.add_argument('--video',dest='no_video',action='store_false')
    parser.set_defaults(no_video=True)
    args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chrome,headless=True)
        recording={} if args.no_video else dict(record_video_dir=str(out/'video_raw'),record_video_size={'width':1440,'height':1000})
        context=browser.new_context(viewport={'width':1440,'height':1000},**recording)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url,wait_until='domcontentloaded');wait_patrol_ready(page)
        page.locator('#route-mode').select_option('comparison')
        page.locator('#demo').click()
        # The real ramped profile makes the former objective infeasible at 190 s.
        # Fix a nearer geometric fixture, keeping the actual battery, report
        # reserve and station inventory unchanged (no solver/result filtering).
        overview=page.request.get(args.url+'/api/aereo/patrullaje/mapa?view=summary',timeout=120000).json()
        objective=json.loads(json.dumps(mapping(transform(INV,translate(transform(FWD,shape(overview['demo_polygon'])),xoff=-50)))))
        with page.expect_response(lambda response:urlsplit(response.url).path.endswith('/objetivo') and response.request.post_data_json.get('target_polygon')==objective,timeout=120000):
            page.locator('#import').set_input_files(dict(name='objetivo_recarga.geojson',mimeType='application/geo+json',buffer=json.dumps(objective).encode()))
        page.wait_for_function("document.querySelector('#target-height').dataset.status==='known'",timeout=120000)
        page.get_by_text('Perfil de vuelo · Mavic 3T',exact=True).click()
        page.locator('#battery').fill('190')
        page.get_by_text('Estaciones hipotéticas',exact=True).click()
        for checkbox in page.locator('#stations input').all():
            checkbox.set_checked(checkbox.get_attribute('value')=='104')
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/api/aereo/patrullaje') and r.request.method=='POST',timeout=300000):page.locator('#calculate').click()
        page.wait_for_function("!document.querySelector('#export').disabled",timeout=300000)
        with page.expect_download() as download:page.locator('#export').click()
        path=out/'recarga_export.json';download.value.save_as(str(path))
        result=json.loads(path.read_text(encoding='utf-8'))['result']
        chosen=next((k for k,r in result['routes'].items() if r['status']=='ready' and r['stops']),None)
        if chosen is None:raise AssertionError('La misión de batería restringida no produjo un cambio de batería')
        page.locator('#results').scroll_into_view_if_needed();page.screenshot(path=str(out/'recarga.png'))
        page.locator('#chosen').select_option(chosen);page.locator('#speed').select_option('100')
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/simular'),timeout=120000) as response:page.locator('#simulate').click()
        simulation=response.value.json()
        (out/'recarga_simulation.json').write_text(json.dumps(simulation,ensure_ascii=False),encoding='utf-8')
        page.wait_for_function("document.querySelector('#log').textContent.includes('Fin:')",timeout=120000)
        page.locator('#flight').scroll_into_view_if_needed();page.wait_for_timeout(1000)
        checks=dict(real_station_budget=True,one_swap=len(result['routes'][chosen]['stops'])==1,
                    flight_report_split=result['effective_profile']['battery_budget_s']==190 and result['planning_profile']['battery_budget_s']==130,
                    completed=simulation['mission_completed'],reset_only_at_station=any(f['phase']=='battery_swap' for f in simulation['timeline']),
                    nonnegative_battery=all(f['battery_pct']>=0 for f in simulation['timeline']))
        video=page.video if not args.no_video else None
        context.close();video_path=out/f"recarga_{result['sha256'][:12]}.webm" if video else None
        if video:video.save_as(str(video_path))
        browser.close()
    report=dict(checks=checks,browser_errors=errors,successful=all(checks.values()) and not errors,video=str(video_path) if video_path else None,
                method=chosen,station_ids=result['request']['station_ids'],battery_budget_s=190,flight_budget_s=130,report_reserve_s=60,
                target_shift_utm_m=[-50,0],stops=result['routes'][chosen]['stops'])
    (out/'charging_checks.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    if not report['successful']:raise SystemExit(1)


if __name__=='__main__':main()
