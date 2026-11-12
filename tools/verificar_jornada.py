"""Live browser check: cached daily routes and automatic flight-to-flight playback."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from tools.browser_ready import wait_patrol_ready


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8080')
    parser.add_argument('--output',default='evidencia/local/jornada')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    errors=[];flights=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport=dict(width=1500,height=1000))
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('response',lambda r:flights.append(r.json()) if urlsplit(r.url).path.endswith('/simular') and r.status==200 else None)
        with page.expect_response(lambda r:urlsplit(r.url).path.endswith('/jornada'),timeout=120000) as response:
            page.goto(args.url,wait_until='domcontentloaded')
        plan=response.value.json();wait_patrol_ready(page)
        page.wait_for_function("!document.querySelector('#play-day').disabled",timeout=30000)
        checks=dict(cached_ready=plan['status']=='ready',two_real_routes=len(plan['flights'])==2 and all(len(f['coordinates'])>3 for f in plan['flights']),
                    no_manual_sector=page.locator('#patrol-catalogue').input_value()=='',two_buttons=page.locator('#daily-flights button').count()==2)
        page.screenshot(path=str(folder/'rutas_del_dia.png'))
        page.locator('#speed').select_option('100');page.locator('#play-day').click()
        page.wait_for_function("document.querySelector('#daily-status').textContent.startsWith('Jornada terminada')",timeout=120000)
        checks.update(two_flights_played=len(flights)==2,landings_at_origin=all(f['patrol_completed'] and f['return_base_id']=='origin' for f in flights),
                      no_teleport=len(flights)==2 and all(abs(a-b)<1e-7 for a,b in zip(flights[0]['timeline'][-1]['coordinates'],flights[1]['timeline'][0]['coordinates'])),
                      stopped_at_end=page.locator('#stop-day').is_disabled(),no_browser_errors=not errors)
        page.screenshot(path=str(folder/'jornada_completada.png'));browser.close()
    report=dict(checks=checks,errors=errors,successful=all(checks.values()))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report));raise SystemExit(not report['successful'])


if __name__=='__main__':main()
