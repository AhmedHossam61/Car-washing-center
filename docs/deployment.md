# Deployment

1. Copy `.env.example` to `.env`.
2. Set `DB_PASSWORD`, `API_KEY`, camera RTSP URLs, and model path.
3. Start the stack with `docker compose up -d --build`.
4. Run migrations with `docker compose exec app alembic upgrade head`.
5. Check `http://localhost:8000/api/v1/health`.
