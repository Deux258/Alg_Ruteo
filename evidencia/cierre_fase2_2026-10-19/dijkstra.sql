SELECT seq,path_seq,node,edge,cost,agg_cost 
FROM pgr_dijkstra
('SELECT id,source,target,length_km AS cost,-1::float8 AS reverse_cost 
FROM routing.edges 
WHERE run_id=''b80f9b83-cad7-53b8-a8b8-34a2a17e614c''::uuid',444204520825800637::bigint,481811177017561201::bigint,true) 
ORDER BY path_seq;
