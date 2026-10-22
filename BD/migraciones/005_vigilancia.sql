-- Publicación adicional: no modifica instantáneas ni APIs previas.
CREATE TABLE routing.patrol_runs (
    id uuid PRIMARY KEY,
    base_run_id uuid NOT NULL REFERENCES routing.runs(run_id),
    input_hash text NOT NULL UNIQUE,
    profile jsonb NOT NULL,
    context jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL CHECK(status IN ('staging','ready'))
);
CREATE TABLE routing.flight_states (
    run_id uuid NOT NULL REFERENCES routing.patrol_runs(id),
    id bigint NOT NULL,
    anchor_id text NOT NULL,
    kind text NOT NULL CHECK(kind IN ('navigation','observation')),
    resolution_m integer NOT NULL CHECK(resolution_m>0),
    surface_m double precision NOT NULL,
    surface_offset_m double precision NOT NULL CHECK(surface_offset_m>0),
    geom geometry(PointZ,32719) NOT NULL,
    PRIMARY KEY(run_id,id),
    UNIQUE(run_id,anchor_id,surface_offset_m)
);
CREATE INDEX flight_states_geom ON routing.flight_states USING gist(geom);
CREATE TABLE routing.flight_edges (
    run_id uuid NOT NULL REFERENCES routing.patrol_runs(id),
    id bigint NOT NULL,
    source bigint NOT NULL,
    target bigint NOT NULL,
    geom geometry(LineStringZ,32719) NOT NULL,
    horizontal_km double precision NOT NULL CHECK(horizontal_km>=0),
    flight_km double precision NOT NULL CHECK(flight_km>0),
    clearance_m double precision,
    surface_known boolean NOT NULL,
    obstacle_distance_m double precision,
    blocked_obstacle boolean NOT NULL,
    profile_samples jsonb NOT NULL,
    PRIMARY KEY(run_id,id),
    FOREIGN KEY(run_id,source) REFERENCES routing.flight_states(run_id,id),
    FOREIGN KEY(run_id,target) REFERENCES routing.flight_states(run_id,id),
    UNIQUE(run_id,source,target), CHECK(source<>target)
);
CREATE INDEX flight_edges_source ON routing.flight_edges(run_id,source);
CREATE TABLE routing.flight_obstacles (
    run_id uuid NOT NULL REFERENCES routing.patrol_runs(id),
    provider_id text NOT NULL,
    kind text NOT NULL,
    height_m double precision,
    original_tags jsonb NOT NULL,
    geom geometry(Geometry,32719) NOT NULL,
    exclusion geometry(Geometry,32719) NOT NULL,
    PRIMARY KEY(run_id,provider_id)
);
CREATE INDEX flight_obstacles_geom ON routing.flight_obstacles USING gist(geom);
CREATE TABLE routing.patrol_datasets (
    run_id uuid NOT NULL REFERENCES routing.patrol_runs(id),
    key text NOT NULL,
    document jsonb NOT NULL,
    PRIMARY KEY(run_id,key)
);
CREATE TABLE routing.patrol_publication (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    run_id uuid NOT NULL REFERENCES routing.patrol_runs(id)
);
CREATE TABLE routing.patrol_evaluations (
    run_id uuid NOT NULL REFERENCES routing.patrol_runs(id),
    sha256 text NOT NULL,
    result jsonb NOT NULL,
    PRIMARY KEY(run_id,sha256)
);
CREATE FUNCTION routing.immutable_patrol() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid;
BEGIN
    rid:=CASE WHEN TG_OP='DELETE' THEN OLD.run_id ELSE NEW.run_id END;
    IF EXISTS(SELECT 1 FROM routing.patrol_runs WHERE id=rid AND status='ready') THEN
        RAISE EXCEPTION 'Publicación de vigilancia inmutable';
    END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER immutable_patrol BEFORE INSERT OR UPDATE OR DELETE ON routing.flight_states FOR EACH ROW EXECUTE FUNCTION routing.immutable_patrol();
CREATE TRIGGER immutable_patrol BEFORE INSERT OR UPDATE OR DELETE ON routing.flight_edges FOR EACH ROW EXECUTE FUNCTION routing.immutable_patrol();
CREATE TRIGGER immutable_patrol BEFORE INSERT OR UPDATE OR DELETE ON routing.flight_obstacles FOR EACH ROW EXECUTE FUNCTION routing.immutable_patrol();
CREATE TRIGGER immutable_patrol BEFORE INSERT OR UPDATE OR DELETE ON routing.patrol_datasets FOR EACH ROW EXECUTE FUNCTION routing.immutable_patrol();
CREATE TRIGGER immutable_evaluation BEFORE UPDATE OR DELETE ON routing.patrol_evaluations FOR EACH ROW EXECUTE FUNCTION routing.immutable_evaluation();
CREATE FUNCTION routing.immutable_patrol_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status='ready' THEN RAISE EXCEPTION 'Publicación de vigilancia inmutable'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER immutable_patrol_run BEFORE UPDATE OR DELETE ON routing.patrol_runs FOR EACH ROW EXECUTE FUNCTION routing.immutable_patrol_run();
