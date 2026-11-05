"""Actual-browser acceptance for distinct corridors, playback and drone perspective. No video."""
import argparse
import itertools
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
from shapely.geometry import shape,LineString,Point
from shapely.ops import transform,unary_union
from core.aerial_data import FWD
from core.patrol_alternatives import corridor_overlap


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:18083')
    parser.add_argument('--chrome',required=True)
    parser.add_argument('--output',default='evidencia/reproductor_2026-11-05')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    checks={};errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chrome,headless=True,args=['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        context=browser.new_context(viewport={'width':1500,'height':1000},accept_downloads=True)
        page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url);page.wait_for_selector('#geo-buildings',timeout=120000);page.wait_for_load_state('networkidle')
        page.locator('#demo').click();page.locator('#focus-target').click()
        checks['target_focus_2d']=page.locator('#focus-target').get_attribute('data-view')=='2d'
        with page.expect_response(lambda r:r.url.endswith('/api/aereo/patrullaje') and r.request.method=='POST',timeout=360000) as response:page.locator('#calculate').click()
        if response.value.status!=200:raise AssertionError(response.value.text())
        page.wait_for_selector('.route-card',timeout=30000)
        with page.expect_download() as exported:page.locator('#export').click()
        exported.value.save_as(str(folder/'mission_export.json'));result=json.loads((folder/'mission_export.json').read_text(encoding='utf-8'))['result']
        alternatives=result['route_alternatives'];checks['four_different_circuits']=len(alternatives)==4
        target=transform(FWD,shape(result['target_polygon']));home=Point(FWD(*result['origin']))
        corridors=[unary_union(LineString(row['coordinates_utm'])).difference(target.buffer(5)).difference(home.buffer(20)) for row in alternatives.values()]
        checks['geometrically_distinct_not_reversed']=all(corridor_overlap(a,b)<=.800001 for a,b in itertools.combinations(corridors,2))
        checks['coverage_and_constraints']=all(r['coverage']['complete'] and r['time_s']<=result['diversity']['maximum_time_s'] for r in alternatives.values())
        checks['default_alternatives_view']=page.locator('#route-mode').input_value()=='alternatives' and page.locator('.route-card').count()==4
        page.locator('#results').scroll_into_view_if_needed();page.screenshot(path=str(folder/'circuitos_distintos.png'))
        page.locator('#route-mode').select_option('comparison')
        checks['four_original_methods_preserved']=all(page.locator('#show-'+method).count()==1 for method in result['routes'])
        checks['coincidence_explained']='coinciden' in page.locator('#diversity-note').inner_text()
        page.locator('#route-mode').select_option('alternatives');page.locator('#chosen').select_option('alt_2')
        page.locator('#show-selected').click();checks['isolate_selected']=page.locator('#results input:checked').count()==1
        page.locator('#speed').select_option('1')
        with page.expect_response(lambda r:r.url.endswith('/simular'),timeout=120000) as response:page.locator('#play').click()
        simulation=response.value.json();(folder/'simulation.json').write_text(json.dumps(simulation,ensure_ascii=False),encoding='utf-8')
        checks['nominal_start_and_land']=simulation['scenario']=='nominal' and not simulation['active_threat_ids'] and simulation['timeline'][0]['time_s']==0 and simulation['timeline'][-1]['phase']=='landed'
        page.wait_for_function("Number(document.querySelector('#player').dataset.time)>0.5",timeout=20000);page.locator('#pause').click()
        paused=float(page.locator('#player').get_attribute('data-time'));page.wait_for_timeout(600)
        checks['pause_holds_clock']=abs(float(page.locator('#player').get_attribute('data-time'))-paused)<.05
        page.locator('#play').click();page.wait_for_timeout(700);page.locator('#pause').click()
        checks['resume_continues_clock']=float(page.locator('#player').get_attribute('data-time'))>paused+.2
        midpoint=simulation['time_s']*.4
        page.locator('#seek').evaluate('(input,value)=>{input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));}',midpoint)
        checks['seek_by_time']=abs(float(page.locator('#player').get_attribute('data-time'))-midpoint)<.2
        page.locator('#finish-playback').click();checks['finish_lands']=page.locator('#player').get_attribute('data-phase')=='landed'
        page.locator('#restart').click();checks['restart_at_ground']=float(page.locator('#player').get_attribute('data-time'))==0 and page.locator('#player').get_attribute('data-phase')=='takeoff'
        page.locator('#seek').evaluate('(input,value)=>{input.value=value;input.dispatchEvent(new Event("input",{bubbles:true}));}',midpoint)
        page.locator('#drone-view').click();page.wait_for_function("document.querySelector('#terrain').dataset.camera==='drone'",timeout=120000)
        checks['real_perspective_camera']=page.locator('#fpv-hud').is_visible() and page.locator('#drone-view').get_attribute('aria-pressed')=='true'
        checks['fpv_no_webgl_error']=page.evaluate("document.querySelector('#terrain').getContext('webgl').getError()===0")
        page.screenshot(path=str(folder/'vista_dron.png'))
        page.locator('#focus-target').click();checks['target_focus_3d']=page.locator('#terrain').get_attribute('data-focus')=='target' and page.locator('#terrain').get_attribute('data-camera')=='orbit'
        page.screenshot(path=str(folder/'objetivo_3d.png'))
        page.locator('#view-toggle').click();page.locator('#focus-target').click()
        checks['target_focus_after_switch']=page.locator('#focus-target').get_attribute('data-view')=='2d'
        page.locator('#draw').click();bounds=page.locator('#map').bounding_box()
        for dx,dy in [(-50,-50),(50,-50),(0,50)]:page.mouse.click(bounds['x']+bounds['width']/2+dx,bounds['y']+bounds['height']/2+dy)
        checks['draw_vertices_count']=page.locator('#draw-tools').get_attribute('data-vertices')=='3'
        page.locator('#undo-vertex').click();checks['undo_vertex']=page.locator('#draw-tools').get_attribute('data-vertices')=='2' and page.locator('#finish').is_disabled()
        page.locator('#cancel-draw').click();checks['cancel_restores_target']=page.locator('#draw-tools').is_hidden() and page.locator('#focus-target').is_enabled()
        page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(500)
        checks['mobile_no_overflow']=page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1');page.screenshot(path=str(folder/'movil.png'))
        page.locator('#demo').click();checks['new_target_invalidates_old_flight']=page.locator('#play').is_disabled() and page.locator('.route-card').count()==0
        context.close();browser.close()
    report=dict(checks=checks,errors=errors,successful=all(checks.values()) and not errors,video=None,
        diversity=result['diversity'],scene_sha256=result['geographic_scene']['sha256'],result_sha256=result['sha256'])
    (folder/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report));raise SystemExit(not report['successful'])


if __name__=='__main__':main()
