# Choreia Learn voice token Worker

`POST /token` (Authorization: Bearer <Google access token of the signed-in learner>) →
`{ value: "ek_...", expires_at, model }` — an OpenAI Realtime ephemeral client secret.
The page then opens a WebRTC session directly with OpenAI (`POST https://api.openai.com/v1/realtime/calls`).

Checks: Google `tokeninfo` (aud = page's OAuth client, verified email, domain in `ALLOWED_DOMAINS`), Origin in `ALLOWED_ORIGINS`.

## Deploy
```
cd worker
npx wrangler deploy
npx wrangler secret put OPENAI_API_KEY   # paste the OpenAI API key once
curl https://choreia-learn-voice.r-yasukouchi.workers.dev/health
```
Model/TTL are `[vars]` in `wrangler.toml` (`gpt-realtime-2.1-mini`, 300 s).
