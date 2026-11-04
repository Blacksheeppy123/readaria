lsof -ti:8000 | xargs kill -9 2>/dev/null
uvicorn backend.api.main:app --reload --host 0.0.0.0 --port 8000