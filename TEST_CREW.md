# How to Test the Multi-Agent Customer Support Crew

## Prerequisites
- Python 3.10+ installed
- Dependencies installed: `pip install -r backend/requirements.txt`
- Valid API key in `.env` file (OpenAI or Ollama Cloud)

## Quick Test Steps

### 1. Start the Server

```bash
# From project root
python -m backend.main
```

**Expected Output:**
```
INFO:     Will watch for changes in these directories: ['D:\\AgenticAI\\AAMAD\\agentic-ai']
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using WatchFiles
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
Initializing Customer Support Crew...
Crew initialized:
  Provider: openai (or ollama)
  Model (low): gpt-4o-mini (or gemma4:31b)
  Model (mid): gpt-4o-mini (or gemma4:31b)
INFO:     Application startup complete.
```

### 2. Test Health Endpoint

**In a new terminal:**
```bash
curl http://localhost:8000/health
```

**Expected Response:**
```json
{"status":"ok"}
```

### 3. View API Documentation

Open in browser: http://localhost:8000/docs

You'll see the interactive Swagger UI with:
- `GET /health` - Health check
- `POST /api/chat` - Chat endpoint
- `GET /api/last-result` - Last result endpoint

### 4. Test the Crew (Path A - Happy Path)

**Test Case:** Customer asks about resetting PIN (KB has answer)

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I reset my B-Mobile My Account PIN?",
    "request_human": false
  }'
```

**Expected Response:**
```json
{
  "response": "To reset your B-Mobile My Account PIN...",
  "decision": "resolve",
  "confidence": 0.85,
  "steps": 4,
  "sources_used": [...],
  "escalation": null,
  "meta": {
    "ai_disclosure": true,
    "elapsed_ms": 15000
  }
}
```

**What to Verify:**
- ✅ `decision` should be `"resolve"`
- ✅ `sources_used` should contain KB article references
- ✅ `escalation` should be `null`
- ✅ Response time under 45 seconds

### 5. Test Path B (Knowledge Gap - Escalation)

**Test Case:** Customer asks about something not in KB

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is your quantum warranty for the hardware drone?",
    "request_human": false
  }'
```

**Expected Response:**
```json
{
  "response": "I don't have information about...",
  "decision": "escalate",
  "confidence": 0.45,
  "steps": 4,
  "sources_used": [],
  "escalation": {
    "ticket_id": "STUB-XXXXXXXX",
    "reason_codes": ["retrieval_gap"],
    "priority": "medium",
    ...
  },
  "meta": {...}
}
```

**What to Verify:**
- ✅ `decision` should be `"escalate"`
- ✅ `reason_codes` should include `"retrieval_gap"` or `"refused"`
- ✅ `escalation.ticket_id` should start with `"STUB-"`
- ✅ Response acknowledges lack of information

### 6. Test Path C (Request Human)

**Test Case:** Customer explicitly requests human agent

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want to talk to a human!",
    "request_human": true
  }'
```

**Expected Response:**
```json
{
  "response": "I'll connect you with a human agent...",
  "decision": "escalate",
  "escalation": {
    "ticket_id": "STUB-XXXXXXXX",
    "reason_codes": ["request_human"],
    "priority": "high",
    ...
  },
  ...
}
```

**What to Verify:**
- ✅ `decision` should be `"escalate"`
- ✅ `reason_codes` should include `"request_human"`
- ✅ `escalation.priority` should be `"high"` or `"medium"`

### 7. Check Prompt Traces

Logs are written to: `project-context/2.build/logs/`

```bash
# View latest trace
ls -lt project-context/2.build/logs/ | head -1
cat project-context/2.build/logs/<trace_id>.json
```

Each trace contains:
- Request details
- Agent outputs
- Execution time
- Model configuration

## Troubleshooting

### Server Won't Start

**Issue:** Server hangs on startup
```bash
# Check if it's a dependency issue
python -c "from backend.crew import CustomerSupportCrew; print('OK')"
```

**Solutions:**
1. Verify all dependencies installed:
   ```bash
   pip install -r backend/requirements.txt
   ```

2. Check API key is valid:
   ```bash
   # Test OpenAI connection
   python -c "import openai; openai.api_key='your-key'; print('OK')"
   ```

3. Try with minimal config:
   ```bash
   # Temporarily disable tools/features
   MAX_ITER=5 python -m backend.main
   ```

### Connection Timeout

**Issue:** `Failed to connect to localhost:8000`

**Solutions:**
1. Check if server is running:
   ```bash
   netstat -ano | findstr :8000
   ```

2. Check for port conflicts:
   ```bash
   # Try different port
   BACKEND_PORT=8001 python -m backend.main
   ```

3. Check firewall settings

### LLM Errors

**Issue:** `Error: Invalid API key` or `Connection refused`

**Solutions:**
1. **OpenAI:**
   ```bash
   # Verify key format (should start with sk-)
   cat .env | grep OPENAI_API_KEY
   ```

2. **Ollama Cloud:**
   ```bash
   # Test Ollama connection
   curl -H "Authorization: Bearer YOUR_OLLAMA_KEY" \
        https://ollama.com/v1/models
   ```

3. **Switch providers:**
   ```env
   # In .env, change:
   LLM_PROVIDER=openai  # or ollama
   ```

### KB Search Not Working

**Issue:** No sources returned even for known queries

**Solutions:**
1. Verify KB file exists:
   ```bash
   cat backend/kb/articles.csv
   ```

2. Check KB configuration in `.env`:
   ```env
   KB_DIR=backend/kb
   KB_FILE=articles.csv
   KB_SIMILARITY_FLOOR=0.35
   ```

3. Try lowering similarity threshold:
   ```env
   KB_SIMILARITY_FLOOR=0.25
   ```

### Timeout Errors

**Issue:** Requests timeout after 45 seconds

**Solutions:**
1. Check model speed (gemma4:31b is slower than gpt-4o-mini)
2. Reduce MAX_ITER:
   ```env
   MAX_ITER=8
   ```
3. Use faster model:
   ```env
   OPENAI_MODEL_LOW=gpt-3.5-turbo
   ```

## Testing Checklist

- [ ] Server starts without errors
- [ ] Health endpoint returns `{"status":"ok"}`
- [ ] Path A (resolve) works with KB query
- [ ] Path B (escalate) works with unknown query
- [ ] Path C (escalate) works with `request_human=true`
- [ ] Prompt traces written to logs directory
- [ ] API documentation accessible at `/docs`
- [ ] Response times under 45 seconds
- [ ] No API key errors in logs

## Advanced Testing

### Load Testing

```bash
# Test concurrent requests
for i in {1..5}; do
  curl -X POST http://localhost:8000/api/chat \
    -H "Content-Type: application/json" \
    -d '{"message":"test"}' &
done
```

### Integration Testing

```bash
# Run with pytest (if tests exist)
pytest backend/tests/
```

### Browser Testing

1. Open http://localhost:8000/docs
2. Click "Try it out" on POST /api/chat
3. Enter test message
4. Execute and view response

## Next Steps

After successful testing:
1. ✅ Backend working - proceed to Frontend integration
2. ✅ Test all three paths (A, B, C)
3. ✅ Review prompt traces for quality
4. ✅ Adjust confidence thresholds if needed
5. ✅ Wire frontend to backend endpoints

## Reference

- **Backend Documentation:** `project-context/2.build/backend.md`
- **API Docs (Interactive):** http://localhost:8000/docs
- **Alternative Docs:** http://localhost:8000/redoc
- **Ollama Setup Guide:** `OLLAMA_SETUP.md`
- **Environment Template:** `.env.example`
