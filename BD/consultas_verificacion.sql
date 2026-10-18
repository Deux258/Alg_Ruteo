-- Ejecutar con psql -v ON_ERROR_STOP=1 sobre la BD del proyecto.
SET TIME ZONE 'UTC';
SELECT version(),postgis_full_version(),pgr_version();
SELECT run_id,status,scope,mode,started_at,finished_at FROM routing.runs ORDER BY started_at;
SELECT run_id,dataset_key,record_count,status,extracted_at FROM routing.datasets ORDER BY run_id,dataset_key;
SELECT routing.topology_report(run_id) FROM routing.publication;
SELECT ST_SRID(geom) AS srid,count(*) FROM routing.graph_base_nodes GROUP BY 1;
SELECT min(cost) AS min_km,max(cost) AS max_km,count(*) AS arcos FROM routing.graph_base_edges;
SELECT count(*) AS extremos_invalidos
FROM routing.graph_base_edges e
JOIN routing.graph_base_nodes a ON a.id=e.source
JOIN routing.graph_base_nodes b ON b.id=e.target
WHERE NOT ST_DWithin(ST_StartPoint(e.geom),a.geom,0.001)
   OR NOT ST_DWithin(ST_EndPoint(e.geom),b.geom,0.001);
-- Selección de ejemplo determinista; no equivale al desarrollo de k rutas.
WITH par AS (SELECT source,target,run_id FROM routing.graph_base_edges ORDER BY id LIMIT 1)
SELECT d.* FROM par,LATERAL pgr_dijkstra(routing.edge_sql(par.run_id),par.source,par.target,true) d;
