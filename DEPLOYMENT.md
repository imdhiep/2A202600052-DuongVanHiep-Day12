# Deployment Information

## Public URL

Pending deployment. The repository is prepared for Railway or Render, but a real public URL still needs to be created from a live cloud account.

## Platform

Recommended: Railway or Render with Redis attached.

## Prepared deployment assets

- Railway config: [06-lab-complete/railway.toml](/d:/python ky 9/day12_ha-tang-cloud_va_deployment/06-lab-complete/railway.toml)
- Render config: [06-lab-complete/render.yaml](/d:/python ky 9/day12_ha-tang-cloud_va_deployment/06-lab-complete/render.yaml)
- Production app: [06-lab-complete/app/main.py](/d:/python ky 9/day12_ha-tang-cloud_va_deployment/06-lab-complete/app/main.py)

## Required environment variables

- `PORT`
- `REDIS_URL`
- `AGENT_API_KEY`
- `JWT_SECRET`
- `MONTHLY_BUDGET_USD`
- `GLOBAL_MONTHLY_BUDGET_USD`
- `RATE_LIMIT_PER_MINUTE`
- `WEB_CONCURRENCY`
- `LOG_LEVEL`

## Test Commands

### Health Check

```bash
curl https://your-agent-domain/health
```

Expected:

```json
{
  "status": "ok"
}
```

### Readiness Check

```bash
curl https://your-agent-domain/ready
```

### Authenticated API Test

```bash
curl -X POST https://your-agent-domain/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test-user","question":"My name is Alice"}'
```

### Conversation Memory Test

```bash
curl -X POST https://your-agent-domain/ask \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test-user","question":"What is my name?"}'
```

Expected behavior: the answer should mention `Alice`.

### Rate Limit Test

```bash
for i in {1..15}; do
  curl -X POST https://your-agent-domain/ask \
    -H "X-API-Key: YOUR_KEY" \
    -H "Content-Type: application/json" \
    -d '{"user_id":"rate-test","question":"test"}'
done
```

Expected behavior: later requests should return `429`.

## Deployment checklist

- Attach Redis before switching to `ENVIRONMENT=production`
- Set a strong `AGENT_API_KEY`
- Set a strong `JWT_SECRET`
- Confirm `/health` returns `200`
- Confirm `/ready` returns `200`
- Confirm `/ask` returns `401` without credentials
- Confirm `/ask` remembers conversation state with the same `user_id`

## Screenshots

- Add cloud dashboard screenshot to `screenshots/dashboard.png`
- Add service status screenshot to `screenshots/service-running.png`
- Add test result screenshot to `screenshots/api-test.png`

## Final note

The codebase is deployment-ready. The only remaining manual step is authenticating to a cloud platform and provisioning the live service plus Redis instance.
