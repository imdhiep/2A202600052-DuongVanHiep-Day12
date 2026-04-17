# Day 12 Lab - Mission Answers

> **Student Name:** Dương Văn Hiệp  
> **Student ID:** 2A202600052  
> **Date:** 17-04-2026

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

1. `OPENAI_API_KEY` is hardcoded directly in `01-localhost-vs-production/develop/app.py`, which would leak secrets if pushed to Git.
2. `DATABASE_URL` is also hardcoded and includes a plaintext password.
3. The app uses debug-oriented settings such as `DEBUG = True` and `reload=True`.
4. It binds to `localhost` instead of `0.0.0.0`, which breaks containers and cloud platforms.
5. The port is fixed to `8000` instead of reading `PORT` from the environment.
6. It uses `print()` logging and even prints secrets.
7. There is no `/health` endpoint.
8. There is no graceful shutdown handling.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcoded in source | Environment-driven via `config.py` | Flexible deploys and safer secret handling |
| Secrets | Stored in code | Injected from env vars | Prevents secret leakage and simplifies rotation |
| Logging | `print()` | Structured JSON logging | Better monitoring and debugging in production |
| Health check | Missing | `GET /health` | Lets the platform detect unhealthy containers |
| Readiness check | Missing | `GET /ready` | Prevents traffic before dependencies are ready |
| Host binding | `localhost` | `0.0.0.0` | Required for containers and public networking |
| Port | Fixed `8000` | `PORT` from env | Required by Railway, Render, and Cloud Run |
| Shutdown | Abrupt | Graceful via signal handling | Protects in-flight requests during restarts |
| Validation | Minimal | Pydantic models | Rejects malformed input safely |
| Deployment mindset | "Works on my machine" | 12-factor style | More consistent behavior across environments |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. Base image: `python:3.11`.
2. Working directory: `/app`.
3. `COPY requirements.txt` is placed early so Docker can cache dependency installation.
4. `CMD` sets the default command, while `ENTRYPOINT` is better when the executable should always run.

### Exercise 2.3: Multi-stage build

- Stage 1 builds and installs dependencies.
- Stage 2 copies only the runtime artifacts into a smaller final image.
- The final image is smaller because it excludes build tooling and caches.

### Exercise 2.3: Image size comparison

- Develop: ~800 MB
- Production: ~160 MB
- Difference: ~80%

These values are documented in `02-docker/README.md` as the expected basic versus advanced comparison.

### Exercise 2.4: Docker Compose stack

```text
Client -> Nginx -> Agent -> Redis
```

- `nginx` is the public entrypoint.
- `agent` serves the FastAPI app.
- `redis` stores shared state for conversation history, rate limiting, and cost guard.

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- URL: [https://day12-production-d371.up.railway.app](https://day12-production-d371.up.railway.app)
- Health URL: [https://day12-production-d371.up.railway.app/health](https://day12-production-d371.up.railway.app/health)
- Screenshot in repo: [screenshots/redis.jpg](/D:/python ky 9/day12_ha-tang-cloud_va_deployment/screenshots/redis.jpg)

### Exercise 3.2: Render deployment

| File | Style | What it controls |
|------|-------|------------------|
| `railway.toml` | Compact platform config | Build strategy, start command, health check, restart policy |
| `render.yaml` | Blueprint style config | Service definition, env vars, Redis attachment, health checks |

### Exercise 3.3: GCP Cloud Run

- `cloudbuild.yaml` defines the build and deployment pipeline.
- `service.yaml` defines the Cloud Run service configuration.
- Cloud Run gives stronger operational control, but setup is more complex than Railway or Render.

## Part 4: API Security

### Exercise 4.1: API key authentication

- The API key is checked in `verify_api_key()` using the `X-API-Key` header.
- Missing or invalid credentials are rejected before the protected endpoint runs.
- Key rotation is done by changing the environment variable and redeploying.

### Exercise 4.2: JWT authentication

JWT flow:

1. Client posts credentials to `POST /auth/token`.
2. Server signs a token containing `sub`, `role`, `iat`, and `exp`.
3. Client sends `Authorization: Bearer <token>` on later requests.
4. Server verifies the token without server-side session storage.

Live verification:

```text
POST /auth/token -> 200
Response keys: access_token, expires_in_minutes, token_type

GET /auth/me with Bearer token -> 200
{"username":"student","role":"admin"}
```

### Exercise 4.3: Rate limiting

- Algorithm: sliding window.
- Limit: `10 requests/minute per user`.
- Shared rate-limit state is stored in Redis in the final project.

Live verification:

```text
Request statuses for one user_id:
200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 429

429 detail:
{
  "detail": {
    "error": "Rate limit exceeded",
    "limit": 10,
    "window_seconds": 60,
    "retry_after_seconds": 41
  }
}
```

### Exercise 4.1-4.3: Test results

```text
GET /health -> 200
{
  "status":"ok",
  "checks":{
    "redis":true,
    "conversation_store":"redis",
    "rate_limiter":"redis",
    "cost_guard":"redis"
  }
}

POST /ask without X-API-Key -> 401

POST /ask with valid X-API-Key -> 200
{
  "user_id":"api-key-check",
  "question":"Hello",
  "answer":"Hello! How can I assist you today?",
  "model":"gpt-4o-mini",
  "storage_backend":"redis"
}
```

### Exercise 4.4: Cost guard implementation

Approach used in the final solution:

- Estimate request cost from token counts.
- Track usage per `user_id` per UTC month.
- Block requests when projected usage would exceed `$10/month per user`.
- Store counters in Redis so all instances share the same budget state.

Live example:

```text
"cost_usd": 9e-06
"budget_usd": 10.0
"budget_remaining_usd": 9.999991
```

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

- `GET /health` is the liveness probe.
- `GET /ready` is the readiness probe.
- Both endpoints were verified live on Railway.

```text
GET /health -> 200
status = ok
redis = true
conversation_store = redis
rate_limiter = redis
cost_guard = redis

GET /ready -> 200
{"ready":true,"storage_backend":"redis"}
```

### Exercise 5.2: Graceful shutdown

- The app handles `SIGTERM`.
- Readiness is turned off during shutdown.
- Uvicorn is configured with graceful shutdown timeout so in-flight requests can complete.

### Exercise 5.3: Stateless design

- Conversation history is stored in Redis.
- Rate-limit state is stored in Redis.
- Cost guard state is stored in Redis.
- This makes the app stateless from the instance perspective.

### Exercise 5.4: Load balancing

- Nginx proxies requests to the app layer.
- Different instances can answer the same user while sharing the same Redis-backed state.

### Exercise 5.5: Test stateless design

Live verification:

```text
POST /ask "My name is Alice" -> instance agent-667ae63d, storage_backend=redis
POST /ask "What is my name?" -> instance agent-b4f74b3e, storage_backend=redis
Answer: "Your name is Alice. I remembered it from this conversation."

GET /users/submission-check-user/history -> 200
message_count = 4
profile.name = Alice
storage_backend = redis
```

This shows that the conversation survived across different instances because state was stored in Redis instead of local memory.

## Part 6: Final Project

### Implementation notes

- The final app is in `06-lab-complete/`.
- It includes `app/main.py`, `app/config.py`, `app/auth.py`, `app/rate_limiter.py`, and `app/cost_guard.py`.
- It also includes `app/conversation_store.py` to keep the code modular.
- Docker uses a multi-stage build and a non-root runtime user.
- Docker Compose includes `agent`, `redis`, and `nginx`.
- The deployed service uses OpenAI API responses with `gpt-4o-mini`, Redis-backed state, API key protection, JWT demo auth, structured logging, health checks, readiness checks, and graceful shutdown.

### Production-readiness verification

```text
python 06-lab-complete/check_production_ready.py
Passed 33/33 checks
```
