from pathlib import Path

p = Path('/app/core/patrol.py')
raw = p.read_bytes()
nl = b'\r\n' if b'\r\n' in raw else b'\n'
text = raw.decode('utf-8').replace('\r\n', '\n')
old_blk = """        adaptive_set = build_adaptive_tasks(graph, target, risk_field_obj, actual['swath_m'], a3_geoms_utm=a3_geoms, forest_zone_utm=graph.forest_zone, terrain=surface, risk_config=r_cfg, task_config=AdaptiveTaskConfig(min_cell_m=max(30.0, r_cfg.min_cell_m)), wind_direction_deg=weather.get('wind_direction_deg'))
        tasks = adaptive_set.tasks if adaptive_set.tasks else sweep_tasks(target, graph)
    else:
        tasks=sweep_tasks(target,graph)
    graph.routing_targets=sorted({home}|{s['node'] for s in stations}|{i for task in tasks for i in task['nodes']})"""
new_blk = """        adaptive_set = build_adaptive_tasks(graph, target, risk_field_obj, actual['swath_m'], a3_geoms_utm=a3_geoms, forest_zone_utm=graph.forest_zone, terrain=surface, risk_config=r_cfg, task_config=AdaptiveTaskConfig(min_cell_m=max(30.0, r_cfg.min_cell_m)), wind_direction_deg=weather.get('wind_direction_deg'))
    tasks = sweep_tasks(target, graph)
    extra_nodes = {i for t in (adaptive_set.tasks if adaptive_set else []) for i in t['nodes']}
    graph.routing_targets=sorted({home}|{s['node'] for s in stations}|{i for task in tasks for i in task['nodes']}|extra_nodes)"""
assert old_blk in text, 'patrol block not found'
out = text.replace(old_blk, new_blk, 1).encode('utf-8')
if nl == b'\r\n':
    out = out.replace(b'\n', b'\r\n')
p.write_bytes(out)

pw = Path('/app/core/web.py')
raww = pw.read_bytes()
nlw = b'\r\n' if b'\r\n' in raww else b'\n'
textw = raww.decode('utf-8').replace('\r\n', '\n')
textw = textw.replace('        with PATROL_LOCK:\n            calculate(m, {', '        calculate(m, {')
textw = textw.replace(
    "                'preferences': {'drone': 'DJI Mavic 3T', 'station_inventory': 1},\n            })\n        logging.info('Prewarm",
    "                'preferences': {'drone': 'DJI Mavic 3T', 'station_inventory': 1},\n        })\n        logging.info('Prewarm",
)
textw = textw.replace('PATROL_LOCK.acquire(timeout=30)', 'PATROL_LOCK.acquire(timeout=90)')
outw = textw.encode('utf-8')
if nlw == b'\r\n':
    outw = outw.replace(b'\n', b'\r\n')
pw.write_bytes(outw)
print('Patched patrol.py and web.py cleanly')
