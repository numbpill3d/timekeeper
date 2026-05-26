"""Kafka topic name constants shared across all services."""

# ingestion -> vision
FRAMES = "omniscient.frames"

# vision -> event-processor
DETECTIONS = "omniscient.detections"

# event-processor -> alert-engine + api (live stream)
EVENTS = "omniscient.events"

# alert-engine -> api / external delivery
ALERTS = "omniscient.alerts"

# Consumer group IDs
GROUP_VISION = "vision-pipeline"
GROUP_EVENT_PROCESSOR = "event-processor"
GROUP_ALERT_ENGINE = "alert-engine"
GROUP_API_STREAMER = "api-live-stream"
