# ST-GCN Agent Rules
1. **NO .ENV FILES**: All API keys and secrets must be read from the local SQLite `app_settings` table or `config.json`. Do not use `os.environ` for user keys.
2. **GRACEFUL FALLBACKS**: Every service integration (Groq, Binance, Supabase) must have a local, keyless fallback. Do not write code that crashes if a key is `None`.
3. **NO MOCKS**: Never use `random` to generate mock data for ML pipelines.
4. **NO N+1 QUERIES**: All database fetches must be batched or vectorized. No SQL queries inside `for` loops.
