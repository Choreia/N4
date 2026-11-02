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
    if (request.method !== 'POST' || !['/token', '/generate', '/tts'].includes(url.pathname)) return json(404, { error: 'not found' });
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

    let body = {};
    try { body = await request.json(); } catch (e) {}
    if (url.pathname === '/generate') return body.kind === 'listening' ? generateListening(body, env, json) : generateQuestions(body, env, json);
    if (url.pathname === '/tts') return tts(body, env, cors);

    // 2. Read the requested session shape (instructions/voice/language come from the page)
    const instructions = String(body.instructions || '').slice(0, 6000);
    const voice = ['marin', 'cedar', 'alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse'].includes(body.voice) ? body.voice : 'marin';
    const language = /^[a-z]{2}$/.test(String(body.language || '')) ? body.language : undefined;
    const speedRaw = parseFloat(body.speed);
    const speed = speedRaw >= 0.5 && speedRaw <= 1.5 ? Math.round(speedRaw * 100) / 100 : undefined; // Realtime output.speed: 0.25–1.5, 1 = default
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
        output: Object.assign({ voice }, speed ? { speed } : {}),
      },
    };

    // 3. Mint the ephemeral client secret
    const safetyId = await sha256Hex(email);
    const mint = (sess) => fetch('https://api.openai.com/v1/realtime/client_secrets', {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + env.OPENAI_API_KEY,
        'Content-Type': 'application/json',
        'OpenAI-Safety-Identifier': safetyId,
      },
      body: JSON.stringify({ expires_after: { anchor: 'created_at', seconds: ttl }, session: sess }),
    });
    let r = await mint(session);
    let data = await r.json().catch(() => ({}));
    if (!r.ok && speed && /speed/i.test(String(data.error && data.error.message || ''))) {
      // API rejected the speed field: retry at default speed rather than failing the session
      delete session.audio.output.speed;
      r = await mint(session);
      data = await r.json().catch(() => ({}));
    }
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

// ---- Question generation (adaptive difficulty) ----
const LEVEL_GUIDE = {
  en: {
    A2: 'CEFR A2: everyday and simple workplace words, present/past/future, short sentences.',
    B1: 'CEFR B1: common business vocabulary, present perfect, conditionals, polite requests, short emails.',
    B2: 'CEFR B2: nuanced business vocabulary, phrasal verbs, collocations, register (formal vs casual), longer emails and reports, inference questions.',
    C1: 'CEFR C1: advanced and formal vocabulary, subtle distinctions between near-synonyms, idioms, hedging, negotiation language, dense passages requiring inference. Distractors must be plausible for an advanced learner.',
  },
  jp: {
    N5: 'JLPT N5: basic everyday vocabulary and kanji, です/ます, particles, very short texts.',
    N4: 'JLPT N4: everyday and simple workplace vocabulary, ～ことができる, ～ようになる, te-form patterns, short notices.',
    N3: 'JLPT N3: workplace vocabulary, intermediate grammar (～ば, ～たばかり, ～ように, 敬語の基本), medium-length emails and notices.',
    N2: 'JLPT N2: abstract and business vocabulary, advanced grammar (～にもかかわらず, ～わけではない, ～ざるを得ない), 敬語, longer business texts with inference.',
    N1: 'JLPT N1: advanced vocabulary, formal/written expressions, subtle grammar distinctions, dense passages. Distractors must be plausible for an advanced learner.',
  },
};
const FORMAT_GUIDE = {
  en: 'The learner is a Japanese adult. Question text (q) and explanation (exp) are for a Japanese reader. Categories and formats:\n' +
      '- vocab: q = "\"<word>\" の意味は？", options a-d are Japanese meanings (a = correct), exp = "例: <natural English example sentence>".\n' +
      '- grammar: q = an English sentence with ＿ for the blank, optionally a short Japanese hint in parentheses; options are English; exp = one-line Japanese explanation of the rule.\n' +
      '- expressions: q = a Japanese situation + "自然な言い方は？"; options are English sentences (a = the natural one); exp = short Japanese note.\n' +
      '- reading: q = a short English passage (email/notice, 2-4 sentences, in quotes) followed by a Japanese comprehension question; options in Japanese or English as natural; exp = short Japanese explanation.',
  jp: 'The learner is an English-speaking adult. Question text (q) and explanation (exp) are for an English reader. Categories and formats:\n' +
      '- vocab: q = "<reading in hiragana> (<kanji>)", options a-d are English meanings (a = correct), exp = short note with one Japanese usage example.\n' +
      '- kanji: q = "How do you read <kanji word>?", options are hiragana readings (a = correct), exp = "<word> = <meaning>".\n' +
      '- grammar: q = a Japanese sentence with ＿ for the blank plus a short English hint in parentheses; options are Japanese; exp = one-line English explanation of the pattern.\n' +
      '- reading: q = a short Japanese passage in 「」 (2-4 sentences, workplace notice/email) followed by an English comprehension question; options in English; exp = short English explanation quoting the key phrase.',
};
const CATS = { en: ['vocab', 'grammar', 'expressions', 'reading'], jp: ['vocab', 'kanji', 'grammar', 'reading'] };

async function generateQuestions(body, env, json) {
  const course = body.course === 'jp' ? 'jp' : 'en';
  const levels = Object.keys(LEVEL_GUIDE[course]);
  const level = levels.includes(body.level) ? body.level : (course === 'jp' ? 'N4' : 'B1');
  const n = Math.min(Math.max(parseInt(body.n, 10) || 20, 1), 40);
  const avoid = Array.isArray(body.avoid) ? body.avoid.map(String).slice(0, 800) : [];
  const mix = course === 'jp' ? { vocab: 0.5, kanji: 0.2, grammar: 0.2, reading: 0.1 } : { vocab: 0.55, grammar: 0.2, expressions: 0.15, reading: 0.1 };
  const counts = {}; let left = n;
  CATS[course].forEach((c, i) => { counts[c] = i === CATS[course].length - 1 ? left : Math.round(n * mix[c]); left -= counts[c]; });
  const dev = 'You write multiple-choice practice questions for a language-learning app. Output JSON only, matching the schema. ' +
    'Exactly one correct option, always placed in "a" (the app shuffles). Distractors must be the same part of speech / same kind and plausible at this level. ' +
    'Each question must introduce ONE new target word or pattern, different from every other question and from the avoid list. Keep q under 200 characters except reading passages (under 400). ' +
    'Level: ' + LEVEL_GUIDE[course][level] + '\n' + FORMAT_GUIDE[course];
  const user = 'Generate ' + n + ' questions: ' + Object.keys(counts).map(c => counts[c] + ' ' + c).join(', ') + '. Topic mix: workplace, email, meetings, IT/software, daily life, travel. ' +
    (avoid.length ? 'Avoid these target words/items (already used): ' + avoid.join(', ') : '');
  const schema = { type: 'object', additionalProperties: false, required: ['questions'], properties: { questions: { type: 'array', items: { type: 'object', additionalProperties: false,
    required: ['cat', 'q', 'a', 'b', 'c', 'd', 'exp'], properties: { cat: { type: 'string', enum: CATS[course] }, q: { type: 'string' }, a: { type: 'string' }, b: { type: 'string' }, c: { type: 'string' }, d: { type: 'string' }, exp: { type: 'string' } } } } } };
  const r = await fetch('https://api.openai.com/v1/responses', { method: 'POST', headers: { Authorization: 'Bearer ' + env.OPENAI_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: env.GEN_MODEL || 'gpt-5.4-mini', reasoning: { effort: 'low' }, input: [{ role: 'developer', content: dev }, { role: 'user', content: user }],
      text: { format: { type: 'json_schema', name: 'questions', strict: true, schema } } }) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return json(r.status, { error: 'openai: ' + (data.error && data.error.message || r.statusText) });
  let txt = data.output_text || '';
  if (!txt) (data.output || []).forEach(o => (o.content || []).forEach(c => { if (c.type === 'output_text') txt += c.text; }));
  let parsed; try { parsed = JSON.parse(txt); } catch (e) { return json(502, { error: 'bad JSON from model' }); }
  const avoidSet = new Set(avoid.map(s => s.toLowerCase()));
  const seen = new Set();
  const rows = (parsed.questions || []).filter(x => x && x.q && x.a && x.b && CATS[course].includes(x.cat)).filter(x => {
    const key = (x.q.match(/[「"“]([^」"”]+)[」"”]/) || [])[1] || x.q; const k = key.toLowerCase();
    if (seen.has(k) || avoidSet.has(k)) return false; seen.add(k); return true;
  }).map(x => [x.cat, x.q, x.a, x.b, x.c || '', x.d || '', 'A', x.exp || '']);
  return json(200, { rows, level, course, model: env.GEN_MODEL || 'gpt-5.4-mini', usage: data.usage || null });
}

// ---- Listening items (audio 4-choice): one sentence + one comprehension question per target word ----
async function generateListening(body, env, json) {
  const course = body.course === 'jp' ? 'jp' : 'en';
  const levels = Object.keys(LEVEL_GUIDE[course]);
  const level = levels.includes(body.level) ? body.level : (course === 'jp' ? 'N4' : 'B1');
  const items = (Array.isArray(body.items) ? body.items : []).slice(0, 40)
    .map(x => ({ id: String(x.id || '').slice(0, 40), word: String(x.word || '').slice(0, 120), avoid: Array.isArray(x.avoid) ? x.avoid.map(String).slice(0, 5) : [] }))
    .filter(x => x.id && x.word);
  if (!items.length) return json(400, { error: 'items required' });
  const lang = course === 'jp' ? 'Japanese' : 'English';
  const dev = 'You write LISTENING comprehension items for a language-learning app. Output JSON only, matching the schema. ' +
    'For each input item write: "sentence" = one short, natural spoken ' + lang + ' sentence (max 25 words / 50 characters for Japanese) that uses the target word in a realistic workplace or daily-life situation; ' +
    '"q" = one simple comprehension question about the sentence, in ' + lang + ', answerable only by listening (who / what / when / where / how many / why); ' +
    '"a" = the correct short answer; "b","c","d" = plausible wrong answers of the same kind (all four similar in length; never "all of the above"). ' +
    'The sentence is heard, not read, so avoid homophones that make it ambiguous, and never put the question inside the sentence. ' +
    (course === 'jp' ? 'Use kanji appropriate for the level with kana otherwise; options may be short Japanese phrases. ' : '') +
    'Do not reuse any sentence listed under avoid. Level: ' + LEVEL_GUIDE[course][level];
  const user = 'Items (id | target word | avoid sentences):\n' + items.map(x => x.id + ' | ' + x.word + (x.avoid.length ? ' | avoid: ' + x.avoid.join(' / ') : '')).join('\n');
  const schema = { type: 'object', additionalProperties: false, required: ['items'], properties: { items: { type: 'array', items: { type: 'object', additionalProperties: false,
    required: ['id', 'sentence', 'q', 'a', 'b', 'c', 'd'], properties: { id: { type: 'string' }, sentence: { type: 'string' }, q: { type: 'string' }, a: { type: 'string' }, b: { type: 'string' }, c: { type: 'string' }, d: { type: 'string' } } } } } };
  const r = await fetch('https://api.openai.com/v1/responses', { method: 'POST', headers: { Authorization: 'Bearer ' + env.OPENAI_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model: env.GEN_MODEL || 'gpt-5.4-mini', reasoning: { effort: 'low' }, input: [{ role: 'developer', content: dev }, { role: 'user', content: user }],
      text: { format: { type: 'json_schema', name: 'listening_items', strict: true, schema } } }) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) return json(r.status, { error: 'openai: ' + (data.error && data.error.message || r.statusText) });
  let txt = data.output_text || '';
  if (!txt) (data.output || []).forEach(o => (o.content || []).forEach(c => { if (c.type === 'output_text') txt += c.text; }));
  let parsed; try { parsed = JSON.parse(txt); } catch (e) { return json(502, { error: 'bad JSON from model' }); }
  const ids = new Set(items.map(x => x.id));
  // row shape = 問題 sheet columns B..I plus ref: [cat, q, a, b, c, d, ans, exp(=spoken script), ref]
  const rows = (parsed.items || []).filter(x => x && ids.has(x.id) && x.sentence && x.q && x.a && x.b)
    .map(x => ['listening', x.q, x.a, x.b, x.c || '', x.d || '', 'A', x.sentence, x.id]);
  return json(200, { rows, level, course, model: env.GEN_MODEL || 'gpt-5.4-mini', usage: data.usage || null });
}

// ---- Text to speech for listening items (cached at the edge by text+speed) ----
const TTS_VOICES = ['marin', 'cedar', 'alloy', 'ash', 'ballad', 'coral', 'echo', 'sage', 'shimmer', 'verse', 'nova', 'onyx', 'fable'];
async function tts(body, env, cors) {
  const corsHeaders = (_r, extra) => Object.assign({}, cors, extra);
  const text = String(body.text || '').trim().slice(0, 600);
  if (!text) return new Response(JSON.stringify({ error: 'text required' }), { status: 400, headers: corsHeaders(request, { 'Content-Type': 'application/json' }) });
  const speedRaw = parseFloat(body.speed);
  const speed = speedRaw >= 0.5 && speedRaw <= 1.5 ? Math.round(speedRaw * 100) / 100 : 1;
  const voice = TTS_VOICES.includes(body.voice) ? body.voice : 'marin';
  const model = env.TTS_MODEL || 'gpt-4o-mini-tts';
  const key = 'https://tts.cache/' + await sha256Hex(model + '|' + voice + '|' + speed + '|' + text);
  const cache = caches.default;
  let hit = await cache.match(key);
  if (hit) { const h = corsHeaders(request, { 'Content-Type': 'audio/mpeg', 'X-Cache': 'HIT' }); return new Response(hit.body, { status: 200, headers: h }); }
  const mk = (v) => fetch('https://api.openai.com/v1/audio/speech', { method: 'POST', headers: { Authorization: 'Bearer ' + env.OPENAI_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, voice: v, input: text, response_format: 'mp3', speed, instructions: 'Read this once, clearly, for a language learner. ' + (speed < 0.9 ? 'Slow, with small pauses between phrases.' : 'Natural pace.') }) });
  let r = await mk(voice);
  if (!r.ok && voice !== 'alloy') { r = await mk('alloy'); } // older model builds may not know the newest voices
  if (!r.ok) { const d = await r.json().catch(() => ({})); return new Response(JSON.stringify({ error: 'openai: ' + (d.error && d.error.message || r.statusText) }), { status: r.status, headers: corsHeaders(request, { 'Content-Type': 'application/json' }) }); }
  const buf = await r.arrayBuffer();
  await cache.put(key, new Response(buf, { headers: { 'Content-Type': 'audio/mpeg', 'Cache-Control': 'public, max-age=2592000' } }));
  return new Response(buf, { status: 200, headers: corsHeaders(request, { 'Content-Type': 'audio/mpeg', 'X-Cache': 'MISS' }) });
}
