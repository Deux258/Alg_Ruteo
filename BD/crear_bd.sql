-- PostgreSQL 16 + PostGIS + pgRouting. Ejecutar sobre una base vacía existente.
-- CREATE DATABASE se delega a POSTGRES_DB de la imagen. No borrar datos al repetir.
BEGIN;
SELECT pg_advisory_xact_lock(74260101);
CREATE EXTENSION IF NOT EXISTS postgis WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pgrouting WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS routing;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SET LOCAL search_path = routing, public;
SET LOCAL TIME ZONE 'UTC';

CREATE TABLE IF NOT EXISTS schema_migrations (
    version integer PRIMARY KEY, checksum text CHECK (checksum ~ '^[0-9a-f]{64}$'),
    applied_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS sources (
    source_id text PRIMARY KEY, product text NOT NULL, url text,
    description text NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS runs (
    run_id uuid PRIMARY KEY, input_hash text NOT NULL CHECK(input_hash ~ '^[0-9a-f]{64}$'),
    scope text NOT NULL CHECK(scope IN ('base','completo')),
    mode text NOT NULL CHECK(mode IN ('snapshot','online')),
    status text NOT NULL DEFAULT 'staging' CHECK(status IN ('staging','ready','failed')),
    configuration jsonb NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz, error text,
    CHECK(status <> 'ready' OR finished_at IS NOT NULL)
);
CREATE TABLE IF NOT EXISTS datasets (
    dataset_id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES runs ON DELETE CASCADE,
    dataset_key text NOT NULL CHECK(dataset_key IN ('I','M1','M2','M3','M4','A1','A2','A3','A4')),
    source_id text NOT NULL REFERENCES sources, schema_version text NOT NULL,
    observed_at timestamptz NOT NULL, extracted_at timestamptz NOT NULL,
    file_sha256 text NOT NULL CHECK(file_sha256 ~ '^[0-9a-f]{64}$'),
    record_count integer NOT NULL CHECK(record_count>=0),
    status text NOT NULL CHECK(status IN ('valid','empty')),
    lineage jsonb NOT NULL, UNIQUE(run_id,dataset_key),
    CHECK((status='empty')=(record_count=0))
);
CREATE TABLE IF NOT EXISTS nodes (
    run_id uuid NOT NULL, id bigint NOT NULL CHECK(id>0), natural_key text NOT NULL,
    dataset_key text NOT NULL DEFAULT 'I' CHECK(dataset_key='I'),
    kind text NOT NULL CHECK(kind IN ('vigilancia','base_candidata')),
    source_record_id text, geom geometry(Point,32719) NOT NULL,
    PRIMARY KEY(run_id,id), UNIQUE(run_id,natural_key),
    FOREIGN KEY(run_id,dataset_key) REFERENCES datasets(run_id,dataset_key) ON DELETE CASCADE,
    CHECK(NOT ST_IsEmpty(geom) AND ST_IsValid(geom))
);
CREATE TABLE IF NOT EXISTS edges (
    run_id uuid NOT NULL, id bigint NOT NULL CHECK(id>0), natural_key text NOT NULL,
    dataset_key text NOT NULL DEFAULT 'I' CHECK(dataset_key='I'),
    source bigint NOT NULL, target bigint NOT NULL, physical_key text NOT NULL,
    geom geometry(LineString,32719) NOT NULL,
    length_km double precision GENERATED ALWAYS AS (ST_Length(geom)/1000.0) STORED,
    PRIMARY KEY(run_id,id), UNIQUE(run_id,natural_key), UNIQUE(run_id,source,target),
    FOREIGN KEY(run_id,dataset_key) REFERENCES datasets(run_id,dataset_key) ON DELETE CASCADE,
    FOREIGN KEY(run_id,source) REFERENCES nodes(run_id,id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY(run_id,target) REFERENCES nodes(run_id,id) DEFERRABLE INITIALLY DEFERRED,
    CHECK(source<>target), CHECK(NOT ST_IsEmpty(geom) AND ST_IsValid(geom)),
    CHECK(length_km>0 AND length_km<'Infinity'::float8)
);
CREATE INDEX IF NOT EXISTS nodes_geom_gist ON nodes USING gist(geom);
CREATE INDEX IF NOT EXISTS edges_geom_gist ON edges USING gist(geom);
CREATE INDEX IF NOT EXISTS edges_source_idx ON edges(run_id,source);
CREATE INDEX IF NOT EXISTS edges_target_idx ON edges(run_id,target);

-- Los futuros cargadores escriben columnas tipadas y conservan su dataset de origen.
CREATE TABLE IF NOT EXISTS base_metadata (
    run_id uuid NOT NULL, node_id bigint NOT NULL, dataset_key text NOT NULL DEFAULT 'M1' CHECK(dataset_key='M1'),
    provider_id text NOT NULL, name text NOT NULL, commune text, address text, updated_on date,
    PRIMARY KEY(run_id,node_id), UNIQUE(run_id,provider_id),
    FOREIGN KEY(run_id,node_id) REFERENCES nodes(run_id,id) ON DELETE CASCADE,
    FOREIGN KEY(run_id,dataset_key) REFERENCES datasets(run_id,dataset_key) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS landcover (
    run_id uuid NOT NULL, id bigint NOT NULL, dataset_key text NOT NULL DEFAULT 'M2' CHECK(dataset_key='M2'),
    provider_id text NOT NULL, category text NOT NULL, source_year integer CHECK(source_year BETWEEN 1900 AND 2200),
    repaired boolean NOT NULL DEFAULT false, geom geometry(MultiPolygon,32719) NOT NULL,
    PRIMARY KEY(run_id,id), UNIQUE(run_id,provider_id),
    FOREIGN KEY(run_id,dataset_key) REFERENCES datasets(run_id,dataset_key) ON DELETE CASCADE,
    CHECK(NOT ST_IsEmpty(geom) AND ST_IsValid(geom))
);
CREATE INDEX IF NOT EXISTS landcover_geom_gist ON landcover USING gist(geom);
CREATE TABLE IF NOT EXISTS node_elevation (
    run_id uuid NOT NULL, node_id bigint NOT NULL, dataset_key text NOT NULL DEFAULT 'M3' CHECK(dataset_key='M3'),
    elevation_m double precision CHECK(elevation_m BETWEEN -1000 AND 10000),
    quality text NOT NULL CHECK(quality IN ('valid','nodata')),
    PRIMARY KEY(run_id,node_id), FOREIGN KEY(run_id,node_id) REFERENCES nodes(run_id,id) ON DELETE CASCADE,
    FOREIGN KEY(run_id,dataset_key) REFERENCES datasets(run_id,dataset_key) ON DELETE CASCADE,
    CHECK((quality='nodata')=(elevation_m IS NULL))
);
CREATE TABLE IF NOT EXISTS weather (
    run_id uuid NOT NULL, id bigint NOT NULL, dataset_key text NOT NULL DEFAULT 'M4' CHECK(dataset_key='M4'),
    cell geometry(Point,32719) NOT NULL, valid_at timestamptz NOT NULL, issued_at timestamptz,
    temperature_c double precision CHECK(temperature_c BETWEEN -100 AND 80),
    relative_humidity_pct double precision CHECK(relative_humidity_pct BETWEEN 0 AND 100),
    wind_speed_ms double precision CHECK(wind_speed_ms BETWEEN 0 AND 150),
    wind_gust_ms double precision CHECK(wind_gust_ms BETWEEN 0 AND 200),
    wind_direction_deg double precision CHECK(wind_direction_deg>=0 AND wind_direction_deg<360),
    precipitation_mm double precision CHECK(precipitation_mm BETWEEN 0 AND 5000),
    PRIMARY KEY(run_id,id), UNIQUE(run_id,valid_at),
    FOREIGN KEY(run_id,dataset_key) REFERENCES datasets(run_id,dataset_key) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS weather_cell_gist ON weather USING gist(cell);

-- Geometría/estado comunes: eventos e historial se distinguen explícitamente.
CREATE TABLE IF NOT EXISTS hazards (
    run_id uuid NOT NULL, id bigint NOT NULL, dataset_key text NOT NULL,
    kind text NOT NULL CHECK(kind IN ('weather','thermal','airspace','historical')),
    provider_id text NOT NULL, geom geometry(Geometry,32719) NOT NULL,
    state text NOT NULL CHECK(state IN ('active','cleared','unknown','historical')),
    valid_from timestamptz, valid_until timestamptz,
    synthetic boolean NOT NULL DEFAULT false, model_version text NOT NULL,
    PRIMARY KEY(run_id,id), UNIQUE(run_id,id,kind), UNIQUE(run_id,dataset_key,provider_id),
    FOREIGN KEY(run_id,dataset_key) REFERENCES datasets(run_id,dataset_key) ON DELETE CASCADE,
    CHECK((dataset_key,kind) IN (('A1','weather'),('A2','thermal'),('A3','airspace'),('A4','historical'))),
    CHECK((kind='historical')=(state='historical')),
    CHECK(valid_until IS NULL OR valid_from IS NULL OR valid_until>valid_from),
    CHECK(NOT ST_IsEmpty(geom) AND ST_IsValid(geom))
);
CREATE INDEX IF NOT EXISTS hazards_geom_gist ON hazards USING gist(geom);
CREATE INDEX IF NOT EXISTS hazards_validity_idx ON hazards(run_id,kind,valid_from,valid_until);
CREATE TABLE IF NOT EXISTS weather_hazards (
    run_id uuid NOT NULL, hazard_id bigint NOT NULL,
    kind text NOT NULL DEFAULT 'weather' CHECK(kind='weather'),
    weather_id bigint, reason text NOT NULL, PRIMARY KEY(run_id,hazard_id),
    FOREIGN KEY(run_id,hazard_id,kind) REFERENCES hazards(run_id,id,kind) ON DELETE CASCADE,
    FOREIGN KEY(run_id,weather_id) REFERENCES weather(run_id,id)
);
CREATE TABLE IF NOT EXISTS thermal_events (
    run_id uuid NOT NULL, hazard_id bigint NOT NULL,
    kind text NOT NULL DEFAULT 'thermal' CHECK(kind='thermal'),
    acquired_at timestamptz NOT NULL, confidence text,
    fire_radiative_power_mw double precision CHECK(fire_radiative_power_mw>=0 AND fire_radiative_power_mw<'Infinity'::float8),
    buffer_m double precision NOT NULL CHECK(buffer_m>0 AND buffer_m<=10000),
    PRIMARY KEY(run_id,hazard_id),
    FOREIGN KEY(run_id,hazard_id,kind) REFERENCES hazards(run_id,id,kind) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS airspace_zones (
    run_id uuid NOT NULL, hazard_id bigint NOT NULL,
    kind text NOT NULL DEFAULT 'airspace' CHECK(kind='airspace'), code text NOT NULL,
    lower_limit text NOT NULL, upper_limit text NOT NULL, conditions text,
    document_page text NOT NULL, original_record text NOT NULL,
    PRIMARY KEY(run_id,hazard_id), UNIQUE(run_id,code),
    FOREIGN KEY(run_id,hazard_id,kind) REFERENCES hazards(run_id,id,kind) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS historical_risk (
    run_id uuid NOT NULL, hazard_id bigint NOT NULL,
    kind text NOT NULL DEFAULT 'historical' CHECK(kind='historical'),
    ordinal_class smallint NOT NULL CHECK(ordinal_class BETWEEN 1 AND 5),
    class_label text NOT NULL, period_start smallint NOT NULL, period_end smallint NOT NULL,
    PRIMARY KEY(run_id,hazard_id), CHECK(period_end>=period_start),
    FOREIGN KEY(run_id,hazard_id,kind) REFERENCES hazards(run_id,id,kind) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS edge_hazard (
    run_id uuid NOT NULL, edge_id bigint NOT NULL, hazard_id bigint NOT NULL,
    overlap_fraction double precision NOT NULL CHECK(overlap_fraction BETWEEN 0 AND 1),
    blocked boolean NOT NULL, model_version text NOT NULL,
    PRIMARY KEY(run_id,edge_id,hazard_id),
    FOREIGN KEY(run_id,edge_id) REFERENCES edges(run_id,id) ON DELETE CASCADE,
    FOREIGN KEY(run_id,hazard_id) REFERENCES hazards(run_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS profiles (
    profile_key text NOT NULL, version integer NOT NULL CHECK(version>0),
    wind_max_ms double precision NOT NULL CHECK(wind_max_ms>0 AND wind_max_ms<=150),
    temperature_min_c double precision NOT NULL CHECK(temperature_min_c BETWEEN -100 AND 80),
    temperature_max_c double precision NOT NULL CHECK(temperature_max_c BETWEEN -100 AND 80),
    surface_max_m double precision NOT NULL CHECK(surface_max_m BETWEEN -1000 AND 10000),
    exposure_lambda double precision NOT NULL CHECK(exposure_lambda>=0 AND exposure_lambda<'Infinity'::float8),
    detour_factor double precision NOT NULL CHECK(detour_factor>=1 AND detour_factor<=10),
    settings jsonb NOT NULL, PRIMARY KEY(profile_key,version), CHECK(temperature_min_c<temperature_max_c)
);
INSERT INTO profiles VALUES('academico',1,8,-5,40,600,1,1.2,
    '{"k":2,"allowed_landcover":["Bosques","Praderas y Matorrales"],"unknown_exposure":1,"candidate_limit":100,"operationally_certified":false}')
ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS route_sets (
    run_id uuid NOT NULL, id uuid NOT NULL, source bigint NOT NULL, target bigint NOT NULL,
    method text NOT NULL CHECK(method IN ('base','propuesto')),
    profile_key text, profile_version integer, requested_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(run_id,id),
    FOREIGN KEY(run_id) REFERENCES runs ON DELETE CASCADE,
    FOREIGN KEY(run_id,source) REFERENCES nodes(run_id,id),
    FOREIGN KEY(run_id,target) REFERENCES nodes(run_id,id),
    FOREIGN KEY(profile_key,profile_version) REFERENCES profiles(profile_key,version) MATCH FULL,
    CHECK(source<>target),
    CHECK((method='base' AND profile_key IS NULL AND profile_version IS NULL)
       OR (method='propuesto' AND profile_key IS NOT NULL AND profile_version IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS routes (
    run_id uuid NOT NULL, id uuid NOT NULL, set_id uuid NOT NULL, rank smallint NOT NULL CHECK(rank>0),
    length_km double precision NOT NULL CHECK(length_km>0 AND length_km<'Infinity'::float8),
    score double precision NOT NULL CHECK(score>=0 AND score<'Infinity'::float8),
    geom geometry(LineString,32719) NOT NULL,
    PRIMARY KEY(run_id,id), UNIQUE(run_id,set_id,rank),
    FOREIGN KEY(run_id,set_id) REFERENCES route_sets(run_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS route_edges (
    run_id uuid NOT NULL, route_id uuid NOT NULL, seq integer NOT NULL CHECK(seq>0), edge_id bigint NOT NULL,
    PRIMARY KEY(run_id,route_id,seq), UNIQUE(run_id,route_id,edge_id),
    FOREIGN KEY(run_id,route_id) REFERENCES routes(run_id,id) ON DELETE CASCADE,
    FOREIGN KEY(run_id,edge_id) REFERENCES edges(run_id,id)
);
CREATE TABLE IF NOT EXISTS evaluations (
    run_id uuid NOT NULL, set_id uuid NOT NULL, scenario_sha256 text NOT NULL CHECK(scenario_sha256 ~ '^[0-9a-f]{64}$'),
    scenario_count integer NOT NULL CHECK(scenario_count>0), unknown_count integer NOT NULL CHECK(unknown_count>=0),
    resilience double precision NOT NULL CHECK(resilience BETWEEN 0 AND 1),
    results jsonb NOT NULL, PRIMARY KEY(run_id,set_id,scenario_sha256),
    FOREIGN KEY(run_id,set_id) REFERENCES route_sets(run_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS publication (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    run_id uuid NOT NULL REFERENCES runs, published_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION protect_ready_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status='ready' AND (TG_OP='DELETE' OR NEW IS DISTINCT FROM OLD) THEN
        RAISE EXCEPTION 'Run listo % es inmutable',OLD.run_id;
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS protect_ready_run ON runs;
CREATE TRIGGER protect_ready_run BEFORE UPDATE OR DELETE ON runs
    FOR EACH ROW EXECUTE FUNCTION protect_ready_run();

-- Solo staging es modificable. Impide editar un snapshot publicado por accidente.
CREATE OR REPLACE FUNCTION immutable_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid;
BEGIN
    rid := CASE WHEN TG_OP='DELETE' THEN OLD.run_id ELSE NEW.run_id END;
    IF EXISTS(SELECT 1 FROM routing.runs WHERE run_id=rid AND status='ready') THEN
        RAISE EXCEPTION 'Snapshot % es inmutable; crear un run nuevo', rid;
    END IF;
    IF TG_OP='UPDATE' AND OLD.run_id<>NEW.run_id THEN RAISE EXCEPTION 'run_id no se puede modificar'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
DO $$
DECLARE tab text;
BEGIN
    FOREACH tab IN ARRAY ARRAY['datasets','nodes','edges','base_metadata','landcover','node_elevation','weather',
        'hazards','weather_hazards','thermal_events','airspace_zones','historical_risk','edge_hazard'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS immutable_snapshot ON routing.%I',tab);
        EXECUTE format('CREATE TRIGGER immutable_snapshot BEFORE INSERT OR UPDATE OR DELETE ON routing.%I FOR EACH ROW EXECUTE FUNCTION routing.immutable_snapshot()',tab);
    END LOOP;
END $$;

CREATE OR REPLACE FUNCTION check_edge_endpoints() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE e record;
BEGIN
    IF TG_TABLE_NAME='edges' THEN
        FOR e IN SELECT * FROM routing.edges WHERE run_id=NEW.run_id AND id=NEW.id LOOP
            IF NOT EXISTS(SELECT 1 FROM routing.nodes a JOIN routing.nodes b ON b.run_id=a.run_id
                WHERE a.run_id=e.run_id AND a.id=e.source AND b.id=e.target
                  AND ST_DWithin(ST_StartPoint(e.geom),a.geom,0.001)
                  AND ST_DWithin(ST_EndPoint(e.geom),b.geom,0.001)) THEN
                RAISE EXCEPTION 'Arco % no coincide con sus nodos (tolerancia 1 mm)',e.id;
            END IF;
        END LOOP;
    ELSE
        FOR e IN SELECT * FROM routing.edges WHERE run_id=NEW.run_id AND (source=NEW.id OR target=NEW.id) LOOP
            IF NOT EXISTS(SELECT 1 FROM routing.nodes a JOIN routing.nodes b ON b.run_id=a.run_id
                WHERE a.run_id=e.run_id AND a.id=e.source AND b.id=e.target
                  AND ST_DWithin(ST_StartPoint(e.geom),a.geom,0.001)
                  AND ST_DWithin(ST_EndPoint(e.geom),b.geom,0.001)) THEN
                RAISE EXCEPTION 'Cambio de nodo invalida el arco %',e.id;
            END IF;
        END LOOP;
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS check_edge_endpoints ON edges;
CREATE CONSTRAINT TRIGGER check_edge_endpoints AFTER INSERT OR UPDATE ON edges
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_edge_endpoints();
DROP TRIGGER IF EXISTS check_node_endpoints ON nodes;
CREATE CONSTRAINT TRIGGER check_node_endpoints AFTER UPDATE ON nodes
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION check_edge_endpoints();

CREATE OR REPLACE VIEW graph_base_edges AS
SELECT e.id,e.source,e.target,e.length_km AS cost,-1::double precision AS reverse_cost,e.geom,e.run_id,e.length_km
FROM edges e JOIN publication p ON p.run_id=e.run_id;
CREATE OR REPLACE VIEW graph_base_nodes AS
SELECT n.* FROM nodes n JOIN publication p ON p.run_id=n.run_id;

-- SQL controlado: ningún texto SQL se recibe desde formularios o desde JSON externos.
CREATE OR REPLACE FUNCTION edge_sql(p_run uuid) RETURNS text LANGUAGE sql IMMUTABLE AS $$
 SELECT format('SELECT id,source,target,length_km AS cost,-1::float8 AS reverse_cost FROM routing.edges WHERE run_id=%L::uuid ORDER BY id',p_run)
$$;
CREATE OR REPLACE FUNCTION topology_report(p_run uuid) RETURNS jsonb LANGUAGE plpgsql STABLE AS $$
DECLARE q text; nc bigint; ec bigint; isolated bigint; strong jsonb; weak jsonb;
BEGIN
    q:=routing.edge_sql(p_run);
    SELECT count(*) INTO nc FROM routing.nodes WHERE run_id=p_run;
    SELECT count(*) INTO ec FROM routing.edges WHERE run_id=p_run;
    SELECT count(*) INTO isolated FROM routing.nodes n WHERE n.run_id=p_run AND NOT EXISTS(
        SELECT 1 FROM routing.edges e WHERE e.run_id=n.run_id AND (e.source=n.id OR e.target=n.id));
    SELECT COALESCE(jsonb_agg(x ORDER BY size DESC,component),'[]') INTO strong FROM (
        SELECT component,count(*) AS size FROM pgr_strongComponents(q) GROUP BY component
    ) x;
    SELECT COALESCE(jsonb_agg(x ORDER BY size DESC,component),'[]') INTO weak FROM (
        SELECT component,count(*) AS size FROM pgr_connectedComponents(q) GROUP BY component
    ) x;
    RETURN jsonb_build_object('nodes',nc,'directed_edges',ec,'isolated_nodes',isolated,
        'strong_components',strong,'weak_components',weak,
        'strong_count',jsonb_array_length(strong)+isolated,'weak_count',jsonb_array_length(weak)+isolated,
        'srid',32719,'length_unit','km','reverse_cost',-1);
END $$;
CREATE OR REPLACE FUNCTION publish_run(p_run uuid,p_scope text) RETURNS void LANGUAGE plpgsql AS $$
DECLARE required text[]; missing text[]; nr bigint; ne bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(74260102);
    IF NOT EXISTS(SELECT 1 FROM routing.runs WHERE run_id=p_run AND scope=p_scope AND status IN ('staging','ready')) THEN
        RAISE EXCEPTION 'run no publicable: %',p_run;
    END IF;
    required:=CASE WHEN p_scope='completo' THEN ARRAY['I','M1','M2','M3','M4','A1','A2','A3','A4'] ELSE ARRAY['I'] END;
    SELECT array_agg(k) INTO missing FROM unnest(required) k WHERE NOT EXISTS(
        SELECT 1 FROM routing.datasets d WHERE d.run_id=p_run AND d.dataset_key=k AND d.status IN ('valid','empty'));
    IF missing IS NOT NULL THEN RAISE EXCEPTION 'Datasets faltantes: %',missing; END IF;
    SELECT count(*) INTO nr FROM routing.nodes WHERE run_id=p_run;
    SELECT count(*) INTO ne FROM routing.edges WHERE run_id=p_run;
    IF nr<2 OR ne<1 THEN RAISE EXCEPTION 'Grafo vacío o insuficiente'; END IF;
    IF EXISTS(SELECT 1 FROM routing.nodes n WHERE n.run_id=p_run AND NOT EXISTS(
        SELECT 1 FROM routing.edges e WHERE e.run_id=n.run_id AND (e.source=n.id OR e.target=n.id))) THEN
        RAISE EXCEPTION 'Grafo contiene nodos aislados';
    END IF;
    SET CONSTRAINTS ALL IMMEDIATE;
    UPDATE routing.runs SET status='ready',finished_at=COALESCE(finished_at,now()),error=NULL WHERE run_id=p_run;
    INSERT INTO routing.publication VALUES(true,p_run,now()) ON CONFLICT(singleton)
        DO UPDATE SET run_id=EXCLUDED.run_id,published_at=EXCLUDED.published_at;
END $$;
INSERT INTO schema_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
COMMIT;
