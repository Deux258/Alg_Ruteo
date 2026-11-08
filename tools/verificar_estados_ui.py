"""Actual browser UI state tests with deterministic delayed HTTP fixtures; no DB/video."""
import argparse
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from playwright.sync_api import sync_playwright, Error

ROOT=Path(__file__).resolve().parents[1]
ORIGIN='http://127.0.0.1:19087'
METHODS=['dijkstra_distance','dijkstra_weighted','gurobi','annealing']
SHA='a'*64
TIME='2026-11-04T00:00:00+00:00'
BLOCKED_TIME='2026-11-04T01:00:00+00:00'
POLYGON={'type':'Polygon','coordinates':[[[-71.65,-33.10],[-71.649,-33.10],[-71.649,-33.099],[-71.65,-33.099],[-71.65,-33.10]]]}
PROFILE=dict(battery_budget_s=1200,mission_budget_s=3600,verification_s=60,altitude_agl_m=60)


def target_preview(level=30):
    return dict(target_display=dict(status='known',level_m_egm2008=level,
        maximum_surface_m_egm2008=level-30,offset_m=30,polygon_sha256=SHA,
        terrain_sha256=SHA,visual_only=True,vertical_datum='EGM2008'))


def manifest(cut=None):
    geometry=dict(type='Point',coordinates=[-71.65,-33.10])
    result=dict(area=POLYGON,flight_area=POLYGON,demo_polygon=POLYGON,profile=PROFILE,
        engine='deterministic-browser-fixture',reference_time=TIME,
        validation=dict(default_time=TIME),communes=[dict(id='05101',name='Valparaíso'),dict(id='05109',name='Viña del Mar')],
        bases=[dict(provider_id='104',name='Base de prueba',geometry=geometry,candidate=True)],
        weather=[dict(valid_at=time,wind_speed_ms=wind,wind_gust_ms=wind,wind_direction_deg=180,temperature_c=20) for time,wind in [(TIME,2),(BLOCKED_TIME,20)]],
        geography=dict(sha256=SHA,tile_url=ORIGIN+'/tiles/{z}/{x}/{y}.png',source={},counts=dict(buildings=2 if cut=='05109' else 1)),
        resources=dict(terrain=ORIGIN+'/fixture/terrain',render=ORIGIN+'/fixture/render',layers={key:ORIGIN+'/fixture/layer/'+key for key in ['M1','M2','A2','A3','A4','buildings','water','landcover','trees','roads','contours']}))
    return result


def mission(blocked=False):
    routes={}
    for index,key in enumerate(METHODS):
        routes[key]=dict(method=key,label=key,status='blocked' if blocked else 'ready',coordinates=[] if blocked else [[-71.65,-33.10,60],[-71.649,-33.099,60],[-71.65,-33.10,0]],
            coordinates_utm=[] if blocked else [[252691,6334502,60],[252781,6334610,60],[252691,6334502,0]],
            distance_m=None if blocked else 300,time_s=None if blocked else 60,compute_s=.1+index*.01,
            resilience=None if blocked else dict(value=.8,scenarios=1000),coverage=None if blocked else dict(percent=100,complete=True),stops=[],solver=dict(engine=key))
    return dict(sha256=SHA,status='blocked' if blocked else 'ready',routes=routes,
        route_alternatives={} if blocked else {f'alt_{i+1}':dict(row,method=f'alt_{i+1}') for i,row in enumerate(routes.values())},
        recommended=[] if blocked else METHODS[:3],alternative_recommended=[] if blocked else ['alt_1'],
        resilience_leaders=[] if blocked else METHODS,network=dict(nodes=3,directed_edges=4,max_horizontal_link_m=200),
        diversity=dict(count=0 if blocked else 4),effective_profile=PROFILE,stations=[],threats=[],
        diagnostic=dict(reasons=[dict(message='Viento fuera del perfil')]) if blocked else {},
        failure_probabilities=dict(threats=[dict(id='A1',probability_pct=100)]) if blocked else {})


def simulation():
    frames=[dict(time_s=t,coordinates=[-71.65+t/100000,-33.10,0 if phase=='landed' else 60],
                 position_utm=[252691+t,6334502,0 if phase=='landed' else 60],phase=phase,battery_pct=100-t/10)
            for t,phase in [(0,'takeoff'),(10,'patrol'),(60,'landed')]]
    return dict(timeline=frames,time_s=60,scenario='nominal',active_threat_ids=[],detection=None,
                mission_completed=True,result_sha256=SHA,status='completed',seed=1)


class Fixtures:
    def __init__(self):
        self.delays=set();self.pending={};self.calls={}

    def reply(self,route,value):
        try:route.fulfill(status=200,content_type='application/json',body=json.dumps(value))
        except Error as error:
            # Aborting a browser fetch can remove its interception before release.
            if not any(word in str(error).lower() for word in ('invalid interception','target closed','already handled')):raise

    def release(self,kind,value):
        self.reply(self.pending.pop(kind),value)

    def handler(self,route):
        request=route.request;url=urlsplit(request.url);path=url.path
        if url.netloc!=urlsplit(ORIGIN).netloc:
            route.abort();return
        kind=None;value=None
        if path=='/api/aereo/patrullaje/mapa':
            cut=parse_qs(url.query).get('commune_id',[None])[0];value=manifest(cut)
            kind='old-commune' if cut=='05101' else 'map'
        elif path=='/api/aereo/patrullaje/objetivo':
            kind='target-preview';value=target_preview()
        elif path=='/api/aereo/patrullaje/validar':
            body=request.post_data_json;blocked=body.get('time')==BLOCKED_TIME
            value=dict(valid=not blocked,violations=[dict(message='Viento fuera del perfil')] if blocked else [],constraints=dict(
                effective_profile=PROFILE,battery_budget_s=1200,flight_budget_s=1140,report_reserve_s=60,mission_budget_s=3600,mission_flight_budget_s=3540))
        elif path=='/api/aereo/patrullaje':
            self.last_mission_request=request.post_data_json
            kind='mission';value=mission(request.post_data_json.get('time')==BLOCKED_TIME)
        elif path.endswith('/simular'):
            kind='simulation';value=simulation()
        elif path=='/fixture/render':
            kind='render';value=dict(sha256=SHA,render={})
        elif path=='/fixture/terrain':
            value=dict(width=2,height=2,x=[0,500],y=[0,500],origin_utm=[252500,6334300],elevations=[0,0,0,0])
        elif path.startswith('/fixture/layer/'):
            value=dict(type='FeatureCollection',features=[dict(type='Feature',geometry=POLYGON,properties=dict(name='Mapped ground',category='forest'))] if path.endswith('/landcover') else [])
        elif path.startswith('/tiles/'):
            route.abort();return
        else:
            target=ROOT/'Sitio Web'/('patrol.html' if path=='/' else path.lstrip('/'))
            if target.is_file() and target.resolve().is_relative_to((ROOT/'Sitio Web').resolve()):
                route.fulfill(status=200,content_type=mimetypes.guess_type(target.name)[0] or 'application/octet-stream',body=target.read_bytes());return
            route.fulfill(status=404,body='unknown fixture '+path);return
        if kind:
            self.calls[kind]=self.calls.get(kind,0)+1
            if kind in self.delays:self.pending[kind]=route;return
        self.reply(route,value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome',required=True);parser.add_argument('--output',default='evidencia/local/ui_states')
    parser.add_argument('--url',help='Ignored: these tests intercept a separate fixture origin, never a live database')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    checks={};errors=[]
    print('Starting browser UI fixture acceptance',flush=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=args.chrome,headless=True,args=['--enable-webgl','--use-angle=swiftshader','--enable-unsafe-swiftshader'])
        context=browser.new_context(viewport=dict(width=1500,height=1000));fixtures=Fixtures();context.route('**/*',fixtures.handler)
        page=context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
        print('Loading UI fixture modules',flush=True)
        page.goto(ORIGIN);page.wait_for_load_state('networkidle');page.locator('#demo').click();page.wait_for_timeout(250)
        print('Calculating fixture mission',flush=True)
        page.locator('#calculate').click();page.wait_for_selector('.route-card')
        checks['literal_four_way_tie']='Empate entre las cuatro técnicas' in page.locator('#resilience-summary').inner_text()
        checks['separate_flight_and_report_budgets']='1140 s de vuelo + 60 s de reporte' in page.locator('#budget-note').inner_text()

        # Seed blur used to remove cards between pointerdown and click, moving
        # this button and silently losing the new threat. Input must invalidate early.
        page.locator('details:has(#hazard-coordinates) summary').click()
        page.locator('#hazard-coordinates').fill('-71.6495, -33.0995')
        page.locator('#radius').fill('15');page.locator('#probability').fill('80')
        page.locator('#seed').fill('20261106');page.locator('#hazard-coordinate-add').click()
        page.locator('#calculate').click();page.wait_for_selector('.route-card')
        checks['seed_edit_then_add_threat_keeps_click']=len(fixtures.last_mission_request['events'])==1
        page.locator('#focus-target').click();page.locator('#draw').click()
        bounds=page.locator('#map').bounding_box()
        for dx,dy in [(-30,-30),(30,-30),(0,30)]:page.mouse.click(bounds['x']+bounds['width']/2+dx,bounds['y']+bounds['height']/2+dy)
        checks['draw_over_interactive_layer']=page.locator('#draw-tools').get_attribute('data-vertices')=='3'
        x,y=bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2
        page.mouse.move(x,y);page.mouse.down();page.mouse.move(x+60,y+20,steps=5);page.mouse.up()
        checks['drag_during_edit_does_not_add_vertex']=page.locator('#draw-tools').get_attribute('data-vertices')=='3'
        page.locator('#undo-vertex').click();checks['undo_vertex_over_interactive_layer']=page.locator('#draw-tools').get_attribute('data-vertices')=='2'
        page.locator('#cancel-draw').click()

        fixtures.delays.add('simulation');page.locator('#play').click();page.wait_for_timeout(100)
        page.locator('#clear-fire').click();fixtures.delays.remove('simulation');fixtures.release('simulation',simulation());page.wait_for_timeout(150)
        checks['cleared_focus_cannot_restore_old_flight']=page.locator('#player').get_attribute('data-phase')=='idle' and page.locator('#log').inner_text()==''

        page.locator('#play').click();page.wait_for_function("document.querySelector('#player').dataset.phase!=='idle'");page.locator('#pause').click()
        fixtures.delays.add('render');page.locator('#drone-view').click();page.wait_for_timeout(100)
        page.locator('#chosen').select_option('alt_2');fixtures.delays.remove('render');fixtures.release('render',dict(sha256=SHA,render={}));page.wait_for_timeout(300)
        checks['changed_route_during_camera_load_keeps_fpv_off']=page.locator('#drone-view').get_attribute('aria-pressed')=='false' and page.locator('#fpv-hud').is_hidden()

        page.locator('#seed').fill('2');page.locator('#seed').dispatch_event('change');page.wait_for_timeout(250)
        fixtures.delays.add('mission');before=fixtures.calls['mission'];page.locator('#calculate').click();page.wait_for_timeout(100)
        checks['duplicate_calculation_control_disabled']=page.locator('#calculate').is_disabled() and fixtures.calls['mission']==before+1
        page.locator('#seed').fill('3');page.locator('#seed').dispatch_event('change');fixtures.delays.remove('mission');fixtures.release('mission',mission());page.wait_for_timeout(300)
        checks['changed_seed_drops_delayed_calculation']=page.locator('.route-card').count()==0 and page.locator('#export').is_disabled()

        fixtures.delays.add('old-commune');page.locator('#commune').select_option('05101');page.wait_for_timeout(100)
        page.locator('#commune').select_option('05109');page.wait_for_function("document.querySelector('#count-buildings').textContent==='2'")
        fixtures.delays.remove('old-commune');fixtures.release('old-commune',manifest('05101'));page.wait_for_timeout(150)
        checks['late_commune_response_cannot_replace_newer_selection']=page.locator('#count-buildings').inner_text()=='2'

        page.locator('#weather').select_option(BLOCKED_TIME);page.wait_for_timeout(300)
        checks['blocked_weather_allows_diagnostic_request']=page.locator('#calculate').is_enabled() and 'diagnóstico' in page.locator('#calculate').inner_text()
        page.locator('#calculate').click();page.wait_for_selector('.route-card')
        checks['blocked_weather_keeps_probability_export']=page.locator('.route-card').count()==4 and page.locator('#failures').is_enabled() and page.locator('#play').is_disabled()
        page.screenshot(path=str(folder/'blocked_diagnostic.png'),full_page=True)

        # A separate page starts without WebGL; the operational map must remain usable.
        no_gl=context.new_page();no_gl.on('pageerror',lambda error:errors.append(str(error)))
        no_gl.add_init_script("const original=HTMLCanvasElement.prototype.getContext;HTMLCanvasElement.prototype.getContext=function(kind,...args){return kind==='webgl'?null:original.call(this,kind,...args)}")
        no_gl.goto(ORIGIN);no_gl.wait_for_load_state('networkidle');no_gl.locator('#view-toggle').click();no_gl.wait_for_timeout(300)
        checks['webgl_failure_preserves_2d']=no_gl.locator('#map').is_visible() and no_gl.locator('#terrain').is_hidden() and 'WebGL' in no_gl.locator('#message').inner_text()

        # A previous target's delayed DSM preview must not replace a newer one.
        preview=context.new_page();preview.on('pageerror',lambda error:errors.append(str(error)))
        preview.goto(ORIGIN);preview.wait_for_load_state('networkidle')
        fixtures.delays.add('target-preview');preview.locator('#demo').click()
        for _ in range(200):
            if 'target-preview' in fixtures.pending:break
            preview.wait_for_timeout(20)
        if 'target-preview' not in fixtures.pending:raise AssertionError('No llegó la vista previa retrasada del objetivo')
        obsolete=fixtures.pending.pop('target-preview');fixtures.delays.remove('target-preview')
        preview.locator('#demo').click()
        preview.wait_for_function("document.querySelector('#target-height').dataset.status==='known'")
        fixtures.reply(obsolete,target_preview(999));preview.wait_for_timeout(150)
        checks['late_target_preview_cannot_replace_new_target']='30.0 m' in preview.locator('#target-height').inner_text() and '999' not in preview.locator('#target-height').inner_text()
        context.close();browser.close()
    report=dict(checks=checks,browser_errors=errors,successful=all(checks.values()) and not errors,api='controlled HTTP fixtures; live API acceptance is separate',video=None)
    (folder/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
    raise SystemExit(not report['successful'])


if __name__=='__main__':main()
