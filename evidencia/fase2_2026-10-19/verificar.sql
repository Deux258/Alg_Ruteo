-- Consultas de solo lectura sobre la publicación activa.
SELECT version(),postgis_full_version(),pgr_version();
SELECT d.dataset_key,d.record_count,d.status
FROM routing.datasets d JOIN routing.publication p USING(run_id)
WHERE p.singleton ORDER BY d.dataset_key;
SELECT a.role,ST_Area(a.geom)/1000000 AS area_km2,a.buffer_m
FROM routing.run_areas a JOIN routing.publication p USING(run_id) WHERE p.singleton;
SELECT b.provider_id,b.name,b.candidate,b.inside_study,b.distance_to_study_m
FROM routing.base_catalogue b JOIN routing.publication p USING(run_id)
WHERE p.singleton ORDER BY b.provider_id;
SELECT 'nodes' AS kind,count(*) FROM routing.nodes n JOIN routing.publication p USING(run_id)
UNION ALL SELECT 'edges',count(*) FROM routing.edges e JOIN routing.publication p USING(run_id)
UNION ALL SELECT 'elevations',count(*) FROM routing.node_elevation n JOIN routing.publication p USING(run_id);
SELECT b.provider_id,z.code AS excluded_by_aip
FROM routing.base_catalogue b JOIN routing.publication p USING(run_id)
JOIN routing.hazards h ON h.run_id=b.run_id AND h.dataset_key='A3' AND ST_Intersects(b.geom,h.geom)
JOIN routing.airspace_zones z ON z.run_id=h.run_id AND z.hazard_id=h.id
WHERE p.singleton AND b.candidate;
SELECT e.evaluation_sha256,e.scenario_sha256,e.result->'metrics' AS metrics
FROM routing.mission_evaluations e JOIN routing.publication p USING(run_id) WHERE p.singleton;
