# Deployment Information

> **Student Name:** Dương Văn Hiệp  
> **Student ID:** 2A202600052  
> **Verified Date:** 17-04-2026

## Public URL

[https://day12-production-d371.up.railway.app](https://day12-production-d371.up.railway.app)

## Platform

Railway

## Test Commands

### Health Check

```bash
curl https://day12-production-d371.up.railway.app/health
```

Expected live output:

```json
{
  "status": "ok",
  "checks": {
    "redis": true,
    "conversation_store": "redis",
    "rate_limiter": "redis",
    "cost_guard": "redis"
  }
}
```

### Readiness Check

```bash
curl https://day12-production-d371.up.railway.app/ready
```

Expected live output:

```json
{
  "ready": true,
  "storage_backend": "redis"
}
```

### Authentication Required

```bash
curl -X POST https://day12-production-d371.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
```

Expected: `401 Unauthorized`

### API Test (with authentication)

```bash
curl -X POST https://day12-production-d371.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test","question":"Hello"}'
```

Expected: `200 OK`

Example live response:

```json
{
  "user_id": "api-key-check",
  "question": "Hello",
  "answer": "Hello! How can I assist you today?",
  "model": "gpt-4o-mini",
  "storage_backend": "redis"
}
```

### Conversation Memory Test

```bash
curl -X POST https://day12-production-d371.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"memory-test","question":"My name is Alice"}'

curl -X POST https://day12-production-d371.up.railway.app/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"memory-test","question":"What is my name?"}'
```

Expected: the second answer should mention `Alice`.

### Rate Limiting

```bash
for i in {1..15}; do
  curl -X POST https://day12-production-d371.up.railway.app/ask \
    -H "X-API-Key: YOUR_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"rate-test\",\"question\":\"test $i\"}"
done
```

Expected: request `11` or later should return `429`.

### Optional JWT Demo

```bash
curl -X POST https://day12-production-d371.up.railway.app/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"student","password":"demo123"}'
```

## Environment Variables Set

- `PORT`
- `REDIS_URL`
- `AGENT_API_KEY`
- `JWT_SECRET`
- `OPENAI_API_KEY`
- `LLM_MODEL`
- `RATE_LIMIT_PER_MINUTE`
- `RATE_LIMIT_WINDOW_SECONDS`
- `MONTHLY_BUDGET_USD`
- `GLOBAL_MONTHLY_BUDGET_USD`
- `WEB_CONCURRENCY`
- `LOG_LEVEL`

## Deployment Assets

- Railway config: [06-lab-complete/railway.toml](/D:/python ky 9/day12_ha-tang-cloud_va_deployment/06-lab-complete/railway.toml)
- Render config: [06-lab-complete/render.yaml](/D:/python ky 9/day12_ha-tang-cloud_va_deployment/06-lab-complete/render.yaml)
- Production app: [06-lab-complete/app/main.py](/D:/python ky 9/day12_ha-tang-cloud_va_deployment/06-lab-complete/app/main.py)
- Final project guide: [06-lab-complete/README.md](/D:/python ky 9/day12_ha-tang-cloud_va_deployment/06-lab-complete/README.md)

## Screenshots

- [Redis service screenshot](</D:/python ky 9/day12_ha-tang-cloud_va_deployment/screenshots/redis.jpg>)
- Add Railway app dashboard screenshot to `screenshots/dashboard.png`
- Add service running screenshot to `screenshots/running.png`
- Add API test screenshot to `screenshots/test.png`

## Final Notes

- The deployment is live and verified.
- Redis is connected and active in production.
- The final manual step before submission is adding the remaining screenshots to the `screenshots/` folder.
