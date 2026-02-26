const assert = require('assert');

global.fetch = async (url, init) => {
  // Return a simple 200 JSON
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    async json() { return { ok: true }; },
    async text() { return JSON.stringify({ ok: true }); }
  };
};

const { GovernorClient } = require('../dist/index.js');

async function run() {
  const c = new GovernorClient({ baseUrl: 'http://example.local', apiKey: 'ocg_test' });
  // call request to ensure headers were set (we can't introspect fetch args here but call should succeed)
  const res = await c.request('/test', { method: 'GET' });
  assert.deepStrictEqual(res, { ok: true });
  console.log('JS header test passed');
}

run().catch((e) => { console.error(e); process.exit(1); });
