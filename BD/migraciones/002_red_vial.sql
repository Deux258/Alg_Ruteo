-- Extiende, sin reescribir el DDL inicial ni modificar snapshots publicados.
ALTER TABLE routing.nodes DROP CONSTRAINT nodes_kind_check;
ALTER TABLE routing.nodes ADD CONSTRAINT nodes_kind_check CHECK(kind IN ('vigilancia','vial','base_candidata'));
ALTER TABLE routing.edges ADD COLUMN road_origin jsonb NOT NULL DEFAULT '[]';
ALTER TABLE routing.datasets ADD COLUMN validation jsonb NOT NULL DEFAULT '{}';

CREATE TABLE routing.base_locations (
    run_id uuid PRIMARY KEY REFERENCES routing.runs ON DELETE CASCADE,
    provider_id text NOT NULL, source_id text NOT NULL REFERENCES routing.sources,
    node_id bigint NOT NULL, name text NOT NULL, address text,
    geom geometry(Point,32719) NOT NULL, provenance jsonb NOT NULL,
    FOREIGN KEY(run_id,node_id) REFERENCES routing.nodes(run_id,id),
    CHECK(NOT ST_IsEmpty(geom) AND ST_IsValid(geom))
);
CREATE INDEX base_locations_geom_gist ON routing.base_locations USING gist(geom);

-- Estos estados son memoria del último arco y de secuencias de giro.
-- No son intersecciones ni conexiones geométricas adicionales.
CREATE TABLE routing.road_states (
    run_id uuid NOT NULL, id bigint NOT NULL CHECK(id>0), edge_id bigint NOT NULL,
    context bigint[] NOT NULL, PRIMARY KEY(run_id,id),
    FOREIGN KEY(run_id,edge_id) REFERENCES routing.edges(run_id,id) ON DELETE CASCADE
);
CREATE TABLE routing.road_transitions (
    run_id uuid NOT NULL, id bigint NOT NULL CHECK(id>0),
    source bigint NOT NULL, target bigint NOT NULL, edge_id bigint NOT NULL,
    PRIMARY KEY(run_id,id), UNIQUE(run_id,source,target),
    FOREIGN KEY(run_id,source) REFERENCES routing.road_states(run_id,id) ON DELETE CASCADE,
    FOREIGN KEY(run_id,target) REFERENCES routing.road_states(run_id,id) ON DELETE CASCADE,
    FOREIGN KEY(run_id,edge_id) REFERENCES routing.edges(run_id,id) ON DELETE CASCADE
);
CREATE INDEX road_transitions_source_idx ON routing.road_transitions(run_id,source);
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['base_locations','road_states','road_transitions'] LOOP
        EXECUTE format('CREATE TRIGGER immutable_snapshot BEFORE INSERT OR UPDATE OR DELETE ON routing.%I FOR EACH ROW EXECUTE FUNCTION routing.immutable_snapshot()',tab);
    END LOOP;
END $$;

CREATE FUNCTION routing.road_state_sql(p_run uuid,p_source bigint,p_target bigint DEFAULT NULL)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
SELECT format($q$
    SELECT t.id,t.source,t.target,e.length_km AS cost,-1::float8 AS reverse_cost
    FROM routing.road_transitions t JOIN routing.edges e ON (e.run_id,e.id)=(t.run_id,t.edge_id)
    WHERE t.run_id=%1$L::uuid
    UNION ALL
    SELECT -row_number() OVER (ORDER BY e.id),0::bigint,e.id,e.length_km,-1::float8
    FROM routing.edges e WHERE e.run_id=%1$L::uuid AND e.source=%2$L::bigint
    UNION ALL
    SELECT (-1000000000000::bigint-row_number() OVER (ORDER BY s.id)),s.id,-1::bigint,0::float8,-1::float8
    FROM routing.road_states s JOIN routing.edges e ON (e.run_id,e.id)=(s.run_id,s.edge_id)
    WHERE s.run_id=%1$L::uuid AND e.target=%3$L::bigint
$q$,p_run,p_source,p_target)
$$;

CREATE FUNCTION routing.road_path(p_run uuid,p_source bigint,p_target bigint)
RETURNS TABLE(seq integer,edge_id bigint,source bigint,target bigint,cost_km double precision,geom geometry)
LANGUAGE sql STABLE AS $$
    SELECT (row_number() OVER (ORDER BY p.path_seq))::integer,e.id,e.source,e.target,e.length_km,e.geom
    FROM pgr_dijkstra(routing.road_state_sql(p_run,p_source,p_target),0::bigint,-1::bigint,true) p
    JOIN routing.road_states s ON s.run_id=p_run AND s.id=p.node
    JOIN routing.edges e ON e.run_id=p_run AND e.id=s.edge_id
    ORDER BY p.path_seq
$$;
