from prometheus_client import Counter, Gauge, Histogram

API_REQUESTS = Counter("mobin_api_requests_total", "HTTP requests", ["method", "route", "status"])
API_DURATION = Histogram("mobin_api_duration_seconds", "HTTP request duration", ["method", "route"])
RETRIEVAL_DURATION = Histogram("mobin_retrieval_duration_seconds", "Passage retrieval time")
FIRST_TOKEN_DURATION = Histogram("mobin_first_token_duration_seconds", "First SSE delta latency")
GATEWAY_FAILURES = Counter("mobin_gateway_failures_total", "Gateway failures", ["code"])
QUOTA_DENIALS = Counter("mobin_quota_denials_total", "Question denials", ["code"])
PROVIDER_TOKENS = Counter("mobin_provider_tokens_total", "Provider tokens", ["kind"])
ACTIVE_KNOWLEDGE = Gauge("mobin_active_knowledge", "Active knowledge release", ["version"])

PROVIDER_COST_USD = Counter("mobin_provider_cost_usd_total", "Estimated provider spend in USD")
