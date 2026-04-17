# Lab 12 - Complete Production Agent

This folder contains the final integrated solution for the Day 12 lab. It is structured to match the submission checklist and the instructor rubric for a 9-10 point result.

## What is included

- Multi-stage Docker image with non-root runtime
- FastAPI application split into `config`, `auth`, `rate_limiter`, `cost_guard`, and `conversation_store`
- API key protection for the main `/ask` endpoint
- Optional JWT demo flow for admin endpoints
- Redis-backed conversation history so the app stays stateless across instances
- Sliding-window rate limiting: `10 req/min per user`
- Monthly cost guard: `$10/month per user`
- Health and readiness probes
- Graceful shutdown handling
- Structured JSON logging
- Nginx reverse proxy for local load-balancing tests

## Project structure

```text
06-lab-complete/
|-- app/
|   |-- __init__.py
|   |-- auth.py
|   |-- config.py
|   |-- conversation_store.py
|   |-- cost_guard.py
|   |-- main.py
|   `-- rate_limiter.py
|-- nginx/
|   `-- nginx.conf
|-- utils/
|   `-- mock_llm.py
|-- .dockerignore
|-- .env.example
|-- Dockerfile
|-- check_production_ready.py
|-- docker-compose.yml
|-- railway.toml
|-- render.yaml
`-- requirements.txt
```

## Run locally

1. Create local env file:

```powershell
Copy-Item .env.example .env
```

2. Update the values inside `.env`, especially `OPENAI_API_KEY`, `AGENT_API_KEY`, and `JWT_SECRET`.

3. Start the stack:

```powershell
docker compose up --build
```

4. Test the service:

```powershell
curl http://localhost:18000/health
```

5. Test the protected agent endpoint:

```powershell
curl http://localhost:18000/ask `
  -Method Post `
  -Headers @{ "X-API-Key" = "replace-with-a-long-random-api-key"; "Content-Type" = "application/json" } `
  -Body '{"user_id":"demo-user","question":"My name is Alice"}'
```

6. Check remembered context:

```powershell
curl http://localhost:18000/ask `
  -Method Post `
  -Headers @{ "X-API-Key" = "replace-with-a-long-random-api-key"; "Content-Type" = "application/json" } `
  -Body '{"user_id":"demo-user","question":"What is my name?"}'
```

## Scale test

The stack is ready for load-balancing experiments.

```powershell
docker compose up --build --scale agent=3
```

Requests still go through `http://localhost:18000` because Nginx proxies traffic to the scaled `agent` service, while conversation state remains in Redis.

## Deploy

### Railway

1. Provision a Redis service and copy its `REDIS_URL`.
2. Set environment variables:
   - `AGENT_API_KEY`
   - `JWT_SECRET`
   - `REDIS_URL`
   - `MONTHLY_BUDGET_USD`
   - `GLOBAL_MONTHLY_BUDGET_USD`
3. Deploy using the included `railway.toml`.

### Render

1. Connect the repository as a Blueprint.
2. Create or attach a Redis service.
3. Set the same environment variables as Railway.
4. Deploy using `render.yaml`.

## Production checklist

```powershell
python check_production_ready.py
```

This verifies the required files, code structure, and deployment readiness markers.
