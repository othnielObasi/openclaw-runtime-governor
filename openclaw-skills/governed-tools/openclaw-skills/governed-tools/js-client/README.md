@openclaw/ocg-client
====================

Minimal JavaScript/TypeScript client for the OpenClaw Governor API.

Usage (Node.js):

```js
import GovernorClient from '@openclaw/ocg-client';

const c = new GovernorClient({ baseUrl: 'https://governor.example', apiKey: process.env.GOVERNOR_API_KEY });
await c.ping();
```

In browser contexts do NOT embed API keys in client code; use a server-side proxy.
