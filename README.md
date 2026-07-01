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
   # Edit .env and fill in your API keys (Ollama, OpenAI, Twilio, etc.)
   ```
3. Start the system:
   ```bash
   docker compose up --build
   ```

## Development
- **Dependencies**: The project uses a unified `requirements.txt` at the root.
- **Architecture**:
    - **API**: FastAPI
    - **Frontend**: React + Vite
    - **Mobile**: Expo (React Native)
- **Testing**: Run `pytest` from the project root to run the test suite.

## License
MIT
