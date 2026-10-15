# PLUGIN GUIDE — extend the platform without forking core

Three extension points are designed as plugins: **AI providers**, **processor agents**, and **exporters**. Each is an interface + a single registration point.

> NOTE (unverified against implementation): exact module/class names below are the contract the parallel backend build is implementing. If a name differs in `backend/`, update this doc (and the registration snippet) to match — the pattern stays the same.

## 1. Add a new AI provider

Implement the provider interface in `backend/ai_provider/`:

```python
# backend/ai_provider/my_provider.py
from .base import BaseAIProvider, ProviderResult, HealthStatus

class MyProvider(BaseAIProvider):
    name = "my_provider"          # unique id used in config + admin UI
    capabilities = {"summarize", "translate"}  # subset of: transcribe, summarize,
                                               # translate, vision, tts

    def __init__(self, api_key: str, **opts): ...

    def complete(self, prompt: str, **kw) -> ProviderResult: ...
    def health_check(self) -> HealthStatus: ...   # called every 5 min
```

Register it — **one line** in the provider registry:

```python
# backend/ai_provider/__init__.py (or registry.py)
from .my_provider import MyProvider
register_provider(MyProvider, env_key="MY_PROVIDER_API_KEY")
```

Then add `MY_PROVIDER_API_KEY=<placeholder>` to `.env.example` and the env table in `docs/DEPLOYMENT_GUIDE.md`. The provider manager picks it up automatically for key rotation, health checks, and fallback ordering. Never hardcode a key — read it from env.

## 2. Add a new processor agent

Agents live in `backend/agents/` and are numbered in pipeline order (`agent01_ingestion.py` … `agent08_email.py`):

```python
# backend/agents/agentNN_myagent.py
from .base import BaseAgent, AgentResult

class MyAgent(BaseAgent):
    name = "my_agent"
    # which queue it consumes; reuse an existing one when possible
    queue = "ai_analysis_queue"

    def run(self, ctx: JobContext) -> AgentResult:
        ...  # read ctx.inputs, write ctx.artifacts, return AgentResult(ok=…, data=…)
```

Registration points (all three, one line each):

1. `backend/agents/__init__.py` — import the class.
2. `backend/celery_app/pipeline.py` — insert it into `PIPELINE_STAGES` in execution order.
3. Frontend stage list — add the stage name + Burmese label to the i18n stage map so `/processing/[jobId]` can display it (SSE already forwards `{stage, progress, message}` generically).

Keep agents idempotent: they must safely re-run after a worker crash (read existing artifacts before redoing work).

## 3. Add a new exporter

Exporters produce downloadable artifacts from a finished job (e.g. MP4 is built-in; add WebM, audio-only MP3, thumbnail pack…):

```python
# backend/agents/exporters/my_exporter.py  (or backend/exporters/)
from .base import BaseExporter

class MyExporter(BaseExporter):
    name = "webm"                 # appears as ?format=webm
    content_type = "video/webm"

    def export(self, job: JobRecord, out_dir: Path) -> Path: ...
```

Register in the exporter registry (one line), and the result endpoint serves it:

```
GET /api/results/{job_id}?format=webm
```

> NOTE (unverified against implementation): the `?format=` query param on the results endpoint is a proposed convention — confirm it exists in the backend before documenting it to users.

## Checklist for any plugin PR

- ☐ Interface implemented, no secrets in code (env-only)
- ☐ Registered at the documented registration point(s)
- ☐ Unit test in `backend/tests/` covering success + failure paths
- ☐ `.env.example` updated if a new env var is needed (placeholder only)
- ☐ Docs updated (this file + relevant guide)
- ☐ `scripts/secret_scan.py` passes
