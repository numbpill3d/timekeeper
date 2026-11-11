# Omniscient Home

An AI-powered home surveillance intelligence platform designed for privacy and real-time monitoring.

## Features
- **Real-time CV Pipeline**: YOLOv8 + ByteTrack + OSNet ReID for accurate object tracking.
- **Structured Data**: Detections are aggregated into actionable events and stored in TimescaleDB.
- **Natural Language Querying**: Ask questions like "Where are my keys?" using a powerful RAG + text-to-SQL pipeline.
- **Secure Alerting**: Instant notifications via Twilio/FCM.

## Getting Started

### Prerequisites
- Docker & Docker Compose installed.
- Python 3.10+ installed for local development.

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/<YOUR_USERNAME>/timekeeper.git
   cd timekeeper
   ```
2. Configure your environment:
   ```bash
   cp .env.example .env
   # Edit .env and fill in your local/prod settings and provider secrets.
   ```
3. Start the system:
   ```bash
   docker compose up --build
   ```

### Camera sources

The ingestion service accepts direct RTSP/RTSPS, HTTP(S), HLS, and local-file
URLs. Use a stable location label (for example `front door` or `kitchen`) so
events can be answered in natural language. Vendor cameras that do not expose
a direct stream use the built-in Ring, Nest, Arlo, and Wyze adapters. Configure
the provider camera as `ring://device-id`, `nest://device-id`, `arlo://device-id`,
or `wyze://device-id`; put non-secret endpoint settings in `provider_config`.
Nest also requires `NEST_PROJECT_ID`. Ring uses its authenticated WHEP live
video API; set `provider_config.whep_url` or `RING_WHEP_URL_TEMPLATE`. Arlo
and Wyze can use `provider_config.rtsp_url` for a local bridge, or
`provider_config.whep_url` for a compatible WebRTC bridge. Their adapter does
not pretend a public cloud camera API exists where the vendor does not provide one.

The adapters use each provider's authenticated live session to produce frames
for the same local CV pipeline. They do not store provider passwords or tokens
in the database.

The first query is intentionally evidence-based: it reports recorded events
and timestamps, includes supporting clips when available, and qualifies low
confidence matches instead of inventing an identity or action.

For common item/person/time questions, the query engine also has a
parameterized no-LLM fallback. For example, `did john pick up my keys today?`
searches recorded object and person labels directly and still returns a
timestamped evidence answer while the local model is unavailable.

## Development
- **Dependencies**: Runtime dependencies are in `requirements.txt`; install
  `requirements-dev.txt` for the complete local test environment.
- **Architecture**:
    - **API**: FastAPI
    - **Frontend**: React + Vite
    - **Mobile**: Expo (React Native)
- **Testing**: Run `python -m pip install -r requirements-dev.txt`, then run
  `pytest` from the project root. Use Docker Compose for integration tests.

## License
MIT
