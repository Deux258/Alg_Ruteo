"""Browser acceptance of level targets, readable 3D flight and dual export. No video."""
import argparse
import json
import math
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright
from tools.browser_ready import wait_patrol_ready


def key(point):
    return tuple(round(value, 8 if index < 2 else 5) for index, value in enumerate(point))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:18083')
    parser.add_argument('--chrome', required=True)
    parser.add_argument('--output', default='evidencia/local/mejoras_3d')
    args = parser.parse_args()
    root = args.url.rstrip('/')
    folder = Path(args.output); folder.mkdir(parents=True, exist_ok=True)
    checks, errors, observations = {}, [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=args.chrome, headless=True,
            args=['--enable-webgl', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
        context = browser.new_context(viewport=dict(width=1500, height=1000), accept_downloads=True)
        page = context.new_page(); page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(root,wait_until='domcontentloaded');wait_patrol_ready(page)
        page.locator('#demo').click()
        page.wait_for_function("document.querySelector('#target-height').dataset.status==='known'", timeout=120000)
        checks['target_preview_is_authoritative_horizontal_plane'] = '30 m' in page.locator('#target-height').inner_text()
        with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/patrullaje') and r.request.method == 'POST', timeout=360000) as response:
            page.locator('#calculate').click()
        if response.value.status != 200: raise AssertionError(response.value.text())
        page.wait_for_function("!document.querySelector('#export').disabled", timeout=120000)
        with page.expect_download() as downloaded: page.locator('#export').click()
        downloaded.value.save_as(str(folder/'mission.json'))
        bundle = json.loads((folder/'mission.json').read_text(encoding='utf-8')); result = bundle['result']
        plane = result['target_display']
        checks['target_plane_is_maximum_plus_30m'] = plane['status'] == 'known' and math.isclose(
            plane['level_m_egm2008'] - plane['maximum_surface_m_egm2008'], 30, abs_tol=1e-8)
        checks['original_json_retains_full_graph_and_all_methods'] = bool(result['graph']['geometry']) and len(result['routes']) == 4
        checks['canonical_vertical_profile_declared'] = bool(result.get('vertical_profile'))
        edges = {str(edge['id']): edge for edge in result['graph']['edges']}
        canonical = {}
        for route_set, field in [('comparison', 'routes'), ('alternatives', 'route_alternatives')]:
            for method, route in result.get(field, {}).items():
                if route['status'] != 'ready': continue
                path = []
                for edge_id in route['edge_ids']:
                    edge = edges[str(edge_id)]
                    points = result['graph']['geometry'][edge['geometry_id']]
                    if edge.get('geometry_reversed'): points = list(reversed(points))
                    path.extend(points[1:] if path else points)
                canonical[(route_set, method)] = path
                checks.setdefault('routes_use_exact_canonical_edge_geometry', True)
                checks['routes_use_exact_canonical_edge_geometry'] &= len(path) == len(route['coordinates']) and all(
                    key(a) == key(b) for a, b in zip(path, route['coordinates']))
        checks['all_four_methods_have_feasible_vertical_profiles'] = all(row['status'] == 'ready' for row in result['routes'].values())
        page.locator('#view-toggle').click()
        page.wait_for_function("Number(document.querySelector('#terrain').dataset.sceneVertices)>10000", timeout=120000)
        canvas = page.locator('#terrain')
        page.locator('#terrain-mission').click()
        before = json.loads(canvas.get_attribute('data-route-screen-widths'))
        zoom = float(canvas.get_attribute('data-zoom'))
        page.locator('#terrain-zoom-in').click()
        closer = float(canvas.get_attribute('data-zoom'))
        checks['zoom_increases_scale_and_preserves_line_pixel_width'] = closer > zoom and json.loads(canvas.get_attribute('data-route-screen-widths')) == before
        page.locator('#terrain-zoom-out').click()
        checks['zoom_out_restores_scale'] = math.isclose(float(canvas.get_attribute('data-zoom')), zoom, abs_tol=2e-6)
        checks['thick_routes_have_direction_arrows'] = bool(before) and max(before) >= 6 and min(before) >= 3 and int(canvas.get_attribute('data-route-arrows')) > 0
        checks['smooth_lighting_uses_vertex_normals'] = canvas.get_attribute('data-terrain-style') == 'vertex-normal-lighting-v1'
        selected_base = page.locator('#base option:checked').inner_text()
        base_labels = page.locator('.terrain-annotation[data-kind="base"] .terrain-annotation-label').all_text_contents()
        checks['departure_base_is_named_in_3d'] = selected_base in base_labels
        checks['departure_base_has_recognizable_svg_icon'] = page.locator('.terrain-annotation[data-kind="base"] svg').count() > 0
        page.screenshot(path=str(folder/'objetivo_rutas_bases_3d.png'))

        page.locator('#speed').select_option('1')
        with page.expect_response(lambda r: urlsplit(r.url).path.endswith('/simular'), timeout=120000) as flight:
            page.locator('#play').click()
        simulation = flight.value.json()
        page.wait_for_function("Number(document.querySelector('#player').dataset.time)>0", timeout=20000)
        page.locator('#pause').click()
        chosen_set = page.locator('#route-mode').input_value(); chosen = page.locator('#chosen').input_value()
        path = canonical[(chosen_set, chosen)]
        frames = {key(frame['coordinates']) for frame in simulation['timeline']}
        checks['simulation_replays_exact_planned_vertical_geometry'] = all(key(point) in frames for point in path)
        checks['nominal_simulation_is_safe_and_finishes_on_ground'] = simulation['mission_completed'] and simulation['timeline'][-1]['phase'] == 'landed' and all(frame['battery_pct'] >= 0 for frame in simulation['timeline'])
        # Select a genuine horizontal flight segment, rather than the takeoff or a stop.
        candidates = [(a, b) for a, b in zip(simulation['timeline'], simulation['timeline'][1:])
            if b['time_s'] > a['time_s'] and math.dist(a['coordinates'][:2], b['coordinates'][:2]) > .00002]
        if not candidates: raise AssertionError('No hay un tramo horizontal que reproducir')
        a, b = candidates[len(candidates)//2]; elapsed = (a['time_s'] + b['time_s'])/2
        def seek(seconds):
            page.locator('#seek').evaluate('(input,time)=>{input.value=time;input.dispatchEvent(new Event("input",{bubbles:true}))}', seconds)
        seek(elapsed)
        actual_time = float(page.locator('#player').get_attribute('data-time'))
        alpha = (actual_time-a['time_s'])/(b['time_s']-a['time_s'])
        expected = [x+(y-x)*alpha for x, y in zip(a['coordinates'], b['coordinates'])]
        instrument = page.locator('#drone-coordinates')
        checks['playback_coordinates_match_interpolated_drone'] = all(math.isclose(float(instrument.get_attribute('data-'+name)), value, abs_tol=tolerance)
            for name, value, tolerance in [('longitude', expected[0], 2e-7), ('latitude', expected[1], 2e-7), ('altitude', expected[2], .05)])
        checks['coordinate_labels_preserve_sign_and_vertical_reference'] = all(label in instrument.inner_text() for label in ('Lat -', 'Lon -', 'EGM2008'))
        checks['drone_has_svg_icon_in_orbit'] = page.locator('.terrain-annotation[data-kind="drone"] svg').count() == 1
        page.locator('#drone-view').click()
        page.wait_for_function("document.querySelector('#terrain').dataset.camera==='drone'", timeout=120000)
        checks['fpv_has_coordinates_and_two_upper_propellers'] = page.locator('#fpv-coordinates').inner_text() == instrument.inner_text() and page.locator('#fpv-propellers').is_visible() and page.locator('#fpv-propellers .propeller').count() == 2
        checks['propellers_pause_with_playback'] = page.locator('#fpv-propellers').get_attribute('data-spinning') == 'false'
        page.locator('#play').click(); page.wait_for_timeout(100)
        checks['propellers_spin_during_playback'] = page.locator('#fpv-propellers').get_attribute('data-spinning') == 'true'
        page.locator('#pause').click()
        checks['first_person_has_no_webgl_error'] = page.evaluate("document.querySelector('#terrain').getContext('webgl').getError()===0")
        pixels = page.evaluate("""() => {
            const canvas=document.querySelector('#terrain'), gl=canvas.getContext('webgl');
            const data=new Uint8Array(canvas.width*canvas.height*4); gl.readPixels(0,0,canvas.width,canvas.height,gl.RGBA,gl.UNSIGNED_BYTE,data);
            let different=0; for(let i=0;i<data.length;i+=4) if(Math.abs(data[i]-224)>6||Math.abs(data[i+1]-235)>6||Math.abs(data[i+2]-232)>6) different++;
            return {different_fraction:different/(canvas.width*canvas.height),width:canvas.width,height:canvas.height};
        }""")
        observations['fpv_pixels'] = pixels
        checks['first_person_renders_scene_instead_of_only_clear_color'] = pixels['different_fraction'] > .005
        page.screenshot(path=str(folder/'pov_helices_coordenadas.png'))
        page.locator('#export-format').select_option('geojson')
        with page.expect_download() as downloaded: page.locator('#export').click()
        downloaded.value.save_as(str(folder/'mission.geojson'))
        geojson = json.loads((folder/'mission.geojson').read_text(encoding='utf-8'))
        checks['geojson_contains_both_route_sets_and_simulation_frames'] = geojson['type'] == 'FeatureCollection' and all(
            any(f['id'] == f'route:{route_set}:{method}' for f in geojson['features']) for route_set, method in canonical) and len(
            [f for f in geojson['features'] if f['properties']['kind'] == 'simulation_frame']) == len(simulation['timeline'])
        def two_dimensions(geometry):
            if geometry is None: return True
            if geometry['type'] == 'GeometryCollection': return all(two_dimensions(g) for g in geometry['geometries'])
            def visit(value):
                if not value: return True
                if isinstance(value[0], (int, float)): return len(value) == 2
                return all(visit(part) for part in value)
            return visit(geometry['coordinates'])
        checks['geojson_uses_2d_geometry_and_explicit_egm2008_attributes'] = all(two_dimensions(f['geometry']) for f in geojson['features']) and 'EGM2008' in geojson['metadata']['vertical_reference']
        checks['geojson_preserves_route_height_arrays'] = all(next(f for f in geojson['features'] if f['id'] == f'route:{route_set}:{method}')['properties']['altitudes_m_egm2008'] == [point[2] for point in points] for (route_set, method), points in canonical.items())
        page.locator('#export-format').select_option('json')
        with page.expect_download() as downloaded: page.locator('#export').click()
        downloaded.value.save_as(str(folder/'mission_with_simulation.json'))
        final = json.loads((folder/'mission_with_simulation.json').read_text(encoding='utf-8'))
        checks['legacy_json_keeps_original_result_and_simulation'] = final['result']['sha256'] == result['sha256'] and final['simulation']['timeline'] == simulation['timeline'] and 'comparison_history' in final

        page.locator('#view-toggle').click(); page.locator('#follow-drone').check()
        # Use 20x so pixel quantisation cannot disguise the difference between
        # continuous damped following and the former 250 ms camera jumps.
        page.locator('#speed').select_option('20'); seek(elapsed)
        page.locator('#play').click()
        follow = page.evaluate("""() => new Promise(resolve => {
            const pane=document.querySelector('#map .leaflet-map-pane'), rows=[];
            const start=performance.now(); function tick(now){rows.push({t:now-start,transform:pane.style.transform});
              if(now-start<1200)requestAnimationFrame(tick);else resolve(rows);}requestAnimationFrame(tick);
        })""")
        page.locator('#pause').click()
        changes = sum(a['transform'] != b['transform'] for a, b in zip(follow, follow[1:]))
        observations['follow_updates_in_1_2s'] = changes
        checks['2d_follow_updates_more_often_than_former_250ms_steps'] = changes >= 7
        checks['propellers_hidden_when_back_in_2d'] = page.locator('#fpv-propellers').is_hidden()
        page.locator('#finish-playback').click()
        checks['finish_stops_propellers_and_preserves_coordinates'] = page.locator('#fpv-propellers').get_attribute('data-spinning') == 'false' and 'Lat -' in instrument.inner_text()
        page.set_viewport_size(dict(width=390, height=844)); page.wait_for_timeout(200)
        checks['new_controls_do_not_overflow_mobile'] = page.evaluate('document.documentElement.scrollWidth<=window.innerWidth+1')
        page.screenshot(path=str(folder/'movil_instrumentos.png'))
        context.close(); browser.close()
    report = dict(checks=checks, browser_errors=errors, observations=observations,
        successful=bool(checks) and all(checks.values()) and not errors, video=None, result_sha256=result['sha256'])
    (folder/'checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False)); raise SystemExit(not report['successful'])


if __name__ == '__main__': main()
