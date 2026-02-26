const assert = require('assert');

// Import built JS client
const { GovernorClient } = require('../dist/index.js');

// Mock global.fetch
global.fetch = async (url, init) => {
  // Return a fake successful JSON response for /health
  const ok = true;
  const status = 200;
  const headers = new Map([['content-type', 'application/json']]);
  return {
    ok,
    status,
    headers: {
      get: (k) => headers.get(k),
    },
    async json() {
      return { status: 'ok' };
    },
    async text() {
      return JSON.stringify({ status: 'ok' });
    },
  };
};

async function run() {
  const c = new GovernorClient({ baseUrl: 'http://example.local' });
  const res = await c.ping();
  assert.deepStrictEqual(res, { status: 'ok' });
  console.log('JS client test passed');
}

run().catch((err) => {
  console.error(err);
  process.exit(1);
});
