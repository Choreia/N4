// Choreia Learn - Voice token endpoint
// Verifies the learner's Google access token (same OAuth client as the page), then mints a
// short-lived OpenAI Realtime client secret. The OpenAI API key never reaches the browser.

export default {
  async fetch(request, env) {
    const origin = request.headers.get('Origin') || '';
    const allowedOrigins = (env.ALLOWED_ORIGINS || '').split(',').map(s => s.trim()).filter(Boolean);
    const corsOrigin = allowedOrigins.includes(origin) ? origin : allowedOrigins[0] || '*';
    const cors = {
      'Access-Control-Allow-Origin': corsOrigin,
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
      'Access-Control-Max-Age': '86400',
      'Vary': 'Origin',
    };
    const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json', ...cors } });

    if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors });
    const url = new URL(request.url);
    if (url.pathname === '/health') return json(200, { ok: true, configured: !!env.OPENAI_API_KEY, model: env.REALTIME_MODEL });
    if (request.method !== 'POST' || url.pathname !== '/token') return json(404, { error: 'not found' });
    if (origin && !allowedOrigins.includes(origin)) return json(403, { error: 'origin not allowed' });
    if (!env.OPENAI_API_KEY) return json(503, { error: 'OPENAI_API_KEY is not configured on the server' });

    // 1. Verify the Google access token
    const auth = request.headers.get('Authorization') || '';
    const gtoken = auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
    if (!gtoken) return json(401, { error: 'missing Google token' });
    let info;
    try {
      const r = await fetch('https://oauth2.googleapis.com/tokeninfo?access_token=' + encodeURIComponent(gtoken));
      if (!r.ok) return json(401, { error: 'invalid Google token' });
      info = await r.json();
    } catch (e) {
      return json(502, { error: 'tokeninfo failed' });
    }
    const email = String(info.email || '').toLowerCase();
    const domain = email.split('@')[1] || '';
    const allowedDomains = (env.ALLOWED_DOMAINS || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean);
    if (info.aud !== env.GOOGLE_CLIENT_ID) return json(401, { error: 'token audience mismatch' });
    if (String(info.email_verified) !== 'true' || !email) return json(401, { error: 'email not verified' });
    if (allowedDomains.length && !allowedDomains.includes(domain)) return json(403, { error: 'domain not allowed: ' + domain });

    // 2. Read the requested session shape (instructions/voice/language come from the page)
    let body = {};
    try { body = await request.json(); } catch (e) {}
    const instructions = String(body.instructions || '').slice(0, 6000);
    const voice = ['marin', 'cedar', 'alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse'].includes(body.voice) ? body.voice : 'marin';
    const language = /^[a-z]{2}$/.test(String(body.language || '')) ? body.language : undefined;
    const ttl = Math.min(Math.max(parseInt(env.TOKEN_TTL_SECONDS || '300', 10) || 300, 10), 7200);

    const session = {
      type: 'realtime',
      model: env.REALTIME_MODEL || 'gpt-realtime-2.1-mini',
      instructions: instructions || undefined,
      output_modalities: ['audio'],
      audio: {
        input: {
          transcription: Object.assign({ model: 'gpt-4o-mini-transcribe' }, language ? { language } : {}),
          turn_detection: { type: 'semantic_vad', eagerness: 'medium', create_response: true, interrupt_response: true },
        },
        output: { voice },
      },
    };

    // 3. Mint the ephemeral client secret
    const safetyId = await sha256Hex(email);
    const r = await fetch('https://api.openai.com/v1/realtime/client_secrets', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + env.OPENAI_API_KEY,
        'Content-Type': 'application/json',
        'OpenAI-Safety-Identifier': safetyId,
      },
      body: JSON.stringify({ expires_after: { anchor: 'created_at', seconds: ttl }, session }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) return json(r.status, { error: 'openai: ' + (data.error && data.error.message || r.statusText) });
    const value = data.value || (data.client_secret && data.client_secret.value);
    if (!value) return json(502, { error: 'no client secret in response' });
    return json(200, { value, expires_at: data.expires_at || (data.client_secret && data.client_secret.expires_at), model: session.model, email });
  },
};

async function sha256Hex(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
