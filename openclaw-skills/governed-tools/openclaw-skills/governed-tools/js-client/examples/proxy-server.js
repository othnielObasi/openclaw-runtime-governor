// Hardened server-side proxy for browser-safe use of the Governor API.
// - Requires Authorization: Bearer <PROXY_TOKEN>
// - Uses rate-limiting and CORS; configurable via env vars.

const express = require('express');
const cors = require('cors');
const rateLimit = require('express-rate-limit');
const fetch = (...args) => import('node-fetch').then(({ default: f }) => f(...args));

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;
const GOVERNOR_URL = process.env.GOVERNOR_URL;
const GOVERNOR_API_KEY = process.env.GOVERNOR_API_KEY;
const PROXY_TOKEN = process.env.PROXY_TOKEN; // required for auth
const ALLOWED_ORIGINS = process.env.ALLOWED_ORIGINS || '*';

if (!GOVERNOR_URL) {
  console.error('GOVERNOR_URL must be set');
  process.exit(1);
}

if (!PROXY_TOKEN) {
  console.error('PROXY_TOKEN must be set to enable proxy auth');
  process.exit(1);
}

// CORS config
const corsOptions = {
  origin: (origin, callback) => {
    if (!origin && ALLOWED_ORIGINS === '*') return callback(null, true);
    if (ALLOWED_ORIGINS === '*') return callback(null, true);
    const allowed = ALLOWED_ORIGINS.split(',').map((s) => s.trim());
    if (allowed.includes(origin)) return callback(null, true);
    return callback(new Error('Not allowed by CORS'));
  },
};

app.use(cors(corsOptions));

// Simple rate limiter: default 60 requests per minute per IP
const limiter = rateLimit({ windowMs: 60 * 1000, max: parseInt(process.env.PROXY_RATE_LIMIT || '60', 10) });
app.use(limiter);

// Auth middleware: expect Authorization: Bearer <PROXY_TOKEN>
// Auth middleware: accept either a static bearer token (PROXY_TOKEN) OR a JWT signed with PROXY_JWT_SECRET
const jwt = require('jsonwebtoken');
const PROXY_JWT_SECRET = process.env.PROXY_JWT_SECRET;

app.use((req, res, next) => {
  const h = req.headers['authorization'] || req.headers['Authorization'];
  if (!h || !h.toString().startsWith('Bearer ')) return res.status(401).json({ error: 'missing_auth' });
  const token = h.toString().slice(7).trim();
  if (!token) return res.status(401).json({ error: 'missing_token' });

  // Static token check (legacy)
  if (PROXY_TOKEN && token === PROXY_TOKEN) return next();

  // JWT check
  if (PROXY_JWT_SECRET) {
    try {
      const payload = jwt.verify(token, PROXY_JWT_SECRET);
      // optionally attach payload to request for downstream use
      req.proxyJwt = payload;
      return next();
    } catch (err) {
      return res.status(403).json({ error: 'invalid_jwt', detail: String(err) });
    }
  }

  return res.status(403).json({ error: 'invalid_token' });
});

app.all('/proxy/:path(*)', async (req, res) => {
  const path = req.params.path || '';
  const url = GOVERNOR_URL.replace(/\/$/, '') + '/' + path.replace(/^\//, '');
  try {
    const r = await fetch(url, {
      method: req.method,
      headers: {
        'Content-Type': 'application/json',
        ...(GOVERNOR_API_KEY ? { 'X-API-Key': GOVERNOR_API_KEY } : {}),
      },
      body: ['GET', 'HEAD'].includes(req.method) ? undefined : JSON.stringify(req.body),
    });
    const text = await r.text();
    res.status(r.status).set('content-type', r.headers.get('content-type') || 'text/plain').send(text);
  } catch (err) {
    res.status(502).json({ error: 'proxy_error', detail: String(err) });
  }
});

app.listen(PORT, () => console.log(`proxy listening on ${PORT}`));
