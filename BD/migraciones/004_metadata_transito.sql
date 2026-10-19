-- No altera los snapshots previos. Cada área y catálogo pertenece a un run.
CREATE TABLE routing.run_areas (
    run_id uuid NOT NULL REFERENCES routing.runs ON DELETE CASCADE,
    role text NOT NULL CHECK(role IN ('study','transit')),
    geom geometry(MultiPolygon,32719) NOT NULL,
    buffer_m double precision NOT NULL CHECK(buffer_m>=0),
    PRIMARY KEY(run_id,role), CHECK(ST_IsValid(geom) AND NOT ST_IsEmpty(geom))
);
CREATE TABLE routing.base_catalogue (
    run_id uuid NOT NULL REFERENCES routing.runs ON DELETE CASCADE,
    provider_id text NOT NULL, node_id bigint, name text NOT NULL,
    candidate boolean NOT NULL, inside_study boolean NOT NULL,
    distance_to_study_m double precision NOT NULL CHECK(distance_to_study_m>=0),
    selection_reason text NOT NULL, source_refs jsonb NOT NULL, original_record jsonb NOT NULL,
    geom geometry(Point,32719) NOT NULL, PRIMARY KEY(run_id,provider_id),
    FOREIGN KEY(run_id,node_id) REFERENCES routing.nodes(run_id,id),
    CHECK(candidate=(node_id IS NOT NULL))
);
CREATE INDEX base_catalogue_geom ON routing.base_catalogue USING gist(geom);
ALTER TABLE routing.landcover ADD COLUMN attributes jsonb NOT NULL DEFAULT '{}';
ALTER TABLE routing.landcover ADD COLUMN original_area_ha double precision;
ALTER TABLE routing.landcover ADD COLUMN clipped_area_ha double precision CHECK(clipped_area_ha>=0);
ALTER TABLE routing.landcover ADD COLUMN original_record jsonb NOT NULL DEFAULT '{}';
CREATE TABLE routing.mission_evaluations (
    run_id uuid NOT NULL REFERENCES routing.runs ON DELETE CASCADE,
    evaluation_sha256 text NOT NULL CHECK(evaluation_sha256 ~ '^[a-f0-9]{64}$'),
    scenario_sha256 text NOT NULL CHECK(scenario_sha256 ~ '^[a-f0-9]{64}$'),
    request jsonb NOT NULL, result jsonb NOT NULL,
    PRIMARY KEY(run_id,evaluation_sha256)
);
-- Evaluaciones son anexos de solo inserción, no parte del snapshot publicado.
CREATE FUNCTION routing.immutable_evaluation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Evaluación inmutable'; END $$;
CREATE TRIGGER immutable_evaluation BEFORE UPDATE OR DELETE ON routing.mission_evaluations
FOR EACH ROW EXECUTE FUNCTION routing.immutable_evaluation();
CREATE TRIGGER immutable_snapshot BEFORE INSERT OR UPDATE OR DELETE ON routing.run_areas
FOR EACH ROW EXECUTE FUNCTION routing.immutable_snapshot();
CREATE TRIGGER immutable_snapshot BEFORE INSERT OR UPDATE OR DELETE ON routing.base_catalogue
FOR EACH ROW EXECUTE FUNCTION routing.immutable_snapshot();
