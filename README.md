# Omniscient Home

AI-powered home surveillance intelligence platform.

## Architecture
- **Cameras**
- **Ingestion**: RTSP -> Kafka
- **Vision**: YOLOv8 + ByteTrack + ReID
- **Event Processor**: Aggregates detections into events
- **Query Engine**: RAG + Text-to-SQL + Ollama
- **Alert Engine**: Twilio/FCM
- **API**: FastAPI
- **Web**: React + Vite
- **Mobile**: Expo

## Setup
1. `cp .env.example .env`
2. `docker compose up --build`

## Development
- **Dependencies**: Use unified `requirements.txt` at root.
- **Shared Code**: `shared/omniscient_shared/`
- **Testing**: Run `pytest` from the project root.
