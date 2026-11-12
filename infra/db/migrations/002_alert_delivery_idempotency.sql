-- Prevent Kafka redelivery from sending the same rule/event more than once.

DELETE FROM alert_deliveries older
USING alert_deliveries newer
WHERE older.rule_id = newer.rule_id
  AND older.event_id = newer.event_id
  AND older.id > newer.id;

CREATE UNIQUE INDEX IF NOT EXISTS alert_deliveries_rule_event_idx
    ON alert_deliveries (rule_id, event_id);
