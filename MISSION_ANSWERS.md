# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

1. `OPENAI_API_KEY` is hardcoded directly in `01-localhost-vs-production/develop/app.py`, which would leak secrets if pushed to Git.
2. `DATABASE_URL` is also hardcoded and even includes a plaintext password.
3. The app uses `DEBUG = True` and `reload=True`, which is unsafe for production.
4. It binds to `localhost` instead of `0.0.0.0`, so it will fail inside containers or cloud platforms.
5. The port is fixed to `8000` instead of reading from the `PORT` environment variable.
6. It uses `print()` logging and even prints the API key, which is both noisy and insecure.
7. There is no `/health` endpoint, so the platform cannot detect whether the container should be restarted.
8. There is no graceful shutdown handling, so requests can be interrupted abruptly when the process stops.

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcoded values in code | Environment variables through `config.py` | Makes deployments flexible and prevents committing secrets |
| Secrets | API key and database URL in source | Secrets injected from env | Safer and easier to rotate |
| Logging | `print()` statements | Structured JSON logs | Easier to search, monitor, and debug in production |
| Health check | Missing | `GET /health` | Lets the platform restart unhealthy containers |
| Readiness check | Missing | `GET /ready` | Prevents traffic from reaching the app before dependencies are ready |
| Host binding | `localhost` | `0.0.0.0` | Required for containers and cloud networking |
| Port | Fixed `8000` | `PORT` from env | Required by Railway/Render/Cloud Run |
| Shutdown | Abrupt stop | Graceful shutdown with `SIGTERM` handling | Reduces failed in-flight requests |
| Validation | Minimal | Pydantic request models | Rejects bad input clearly and safely |
| Deployment mindset | "Works on my machine" | 12-factor compliant | App behaves consistently across environments |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. Base image: `python:3.11` in the basic Dockerfile.
2. Working directory: `/app`.
3. `COPY requirements.txt` first so Docker can reuse the cached dependency layer when only source code changes.
4. `CMD` provides the default command and can be overridden easily, while `ENTRYPOINT` is better when the container should always run a specific executable.

### Exercise 2.3: Multi-stage build

- Stage 1 installs build dependencies and Python packages.
- Stage 2 copies only the runtime artifacts that are needed to run the app.
- The final image is smaller because compilers, package caches, and build tooling are not shipped in the runtime image.

### Exercise 2.3: Image size comparison

- Develop: typically much larger because it uses a single full Python image and keeps build tooling in the final result.
- Production: smaller because it uses `python:3.11-slim` and multi-stage copying.
- Difference: usually significant, often around 50% or more, depending on installed dependencies.

Note: exact image size should be confirmed with `docker images` after building on the target machine.

### Exercise 2.4: Docker Compose stack

Architecture:

```text
Client -> Nginx -> Agent -> Redis
```

- `nginx` receives external traffic on port `8000`.
- `agent` runs the FastAPI application.
- `redis` stores conversation history, rate-limit state, and budget state so the app stays stateless.
- Nginx can keep working even if the `agent` service is scaled to multiple replicas.

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- Expected flow:
  - `railway login`
  - `railway init`
  - set `AGENT_API_KEY`, `JWT_SECRET`, `REDIS_URL`, `MONTHLY_BUDGET_USD`
  - `railway up`
- Railway uses `PORT` automatically, so the app must read it from the environment.
- The final project already includes `06-lab-complete/railway.toml` for deployment.

### Exercise 3.2: Render deployment

Comparison of `render.yaml` vs `railway.toml`:

| File | Style | What it controls |
|------|-------|------------------|
| `railway.toml` | Compact platform config | Build strategy, start command, health check, restart policy |
| `render.yaml` | Blueprint / infrastructure-as-code | Web service, env vars, health check, and attached Redis service |

Render's YAML is more declarative for the whole environment, while Railway's TOML is more focused on how to run one deployed service.

### Exercise 3.3: GCP Cloud Run

- `cloudbuild.yaml` defines the CI/CD pipeline.
- `service.yaml` defines the Cloud Run service settings.
- Cloud Run is more production-oriented and gives stronger scaling/control than Railway or Render, but setup is more complex.

## Part 4: API Security

### Exercise 4.1: API key authentication

- The API key is checked inside `verify_api_key()` using the `X-API-Key` header.
- Missing or invalid credentials cause the request to fail before the protected endpoint runs.
- Key rotation is done by changing the environment variable value and redeploying or restarting the service.

### Exercise 4.2: JWT authentication

JWT flow:

1. Client sends username/password to a login endpoint.
2. Server signs a JWT containing identity and role.
3. Client sends `Authorization: Bearer <token>` on later requests.
4. Server verifies the signature and expiration, then extracts user info without querying server-side session state.

### Exercise 4.3: Rate limiting

- Algorithm: sliding window.
- Lab target: `10 requests/minute per user`.
- Admin bypass or higher quota can be implemented by assigning a larger limit to admin identities.
- In the final solution, rate-limit state is stored in Redis when available so it works across multiple instances.

### Exercise 4.4: Cost guard implementation

Approach used in the final solution:

- Estimate request cost from input and output token counts.
- Track usage by `user_id` per UTC month.
- Block new requests when projected spend would exceed `$10/month per user`.
- Also track a global monthly budget for extra safety.
- Persist budget state in Redis when available so scale-out instances share the same spending counters.

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

- `GET /health` is the liveness probe.
- `GET /ready` is the readiness probe.
- `health` tells the platform the process is alive.
- `ready` tells the load balancer whether the app can safely receive traffic.

### Exercise 5.2: Graceful shutdown

- The app handles `SIGTERM` and flips its readiness state off.
- This stops new traffic from being routed in.
- Existing requests can complete during Uvicorn's graceful shutdown timeout.

### Exercise 5.3: Stateless design

- Conversation history is stored in Redis instead of per-process memory.
- Rate-limiter state is stored in Redis.
- Cost guard state is stored in Redis.
- Because of that, multiple instances can answer the same user consistently.

### Exercise 5.4: Load balancing

- Nginx sits in front of the FastAPI app.
- Traffic enters through one endpoint and is proxied to the `agent` service.
- When scaling with `docker compose up --scale agent=3`, the reverse proxy layer keeps a stable public entrypoint.

### Exercise 5.5: Test stateless design

How to verify:

1. Send a message like `"My name is Alice"` with a fixed `user_id`.
2. Send a second message `"What is my name?"`.
3. Scale the app or restart one instance.
4. Send the second message again.
5. The reply should still contain `Alice`, proving state is not tied to a single process.

## Part 6: Final Project

### Implementation notes

- The final app lives in `06-lab-complete/`.
- It meets the requested structure with `app/main.py`, `app/config.py`, `app/auth.py`, `app/rate_limiter.py`, and `app/cost_guard.py`.
- It also adds `app/conversation_store.py` to keep the code modular and the main file clean.
- Docker uses a multi-stage build and a non-root runtime user.
- Docker Compose includes `agent`, `redis`, and `nginx`.
- The app supports conversation history by `user_id`, health/readiness checks, API key auth, JWT demo auth, rate limiting, cost guard, structured logging, and graceful shutdown.

### Test results summary

- Missing API key: should return `401`.
- Valid API key with valid body: should return `200`.
- Repeated requests from one `user_id`: should eventually return `429`.
- Invalid request body: should return `422`.
- Health check: should return `200`.
- Readiness check: should return `200` when dependencies are ready, otherwise `503`.

### Remaining deployment step

The repository is deployment-ready, but the actual public URL must be added after deploying from a real Railway or Render account with Redis configured.
