-- Extensión compatible: los snapshots viales previos permanecen inmutables.
ALTER TABLE routing.nodes DROP CONSTRAINT nodes_kind_check;
ALTER TABLE routing.nodes ADD CONSTRAINT nodes_kind_check
    CHECK(kind IN ('vigilancia','vial','base_candidata','navegacion'));
CREATE TABLE routing.aerial_models (
    run_id uuid PRIMARY KEY REFERENCES routing.runs ON DELETE CASCADE,
    profile jsonb NOT NULL, context jsonb NOT NULL,
    clearance_verified boolean NOT NULL DEFAULT false CHECK(NOT clearance_verified)
);
CREATE TRIGGER immutable_snapshot BEFORE INSERT OR UPDATE OR DELETE ON routing.aerial_models
FOR EACH ROW EXECUTE FUNCTION routing.immutable_snapshot();
