const FORWARDED_HEADERS = [
  'accept',
  'content-type',
  'cookie',
  'origin',
  'x-agrivision-request',
];

export default async function handler(request, response) {
  const configuredOrigin = process.env.BACKEND_API_ORIGIN;
  if (!configuredOrigin) {
    response.status(503).json({ detail: 'The advisory service is not configured.' });
    return;
  }

  let backendOrigin;
  try {
    backendOrigin = new URL(configuredOrigin);
  } catch {
    response.status(503).json({ detail: 'The advisory service is not configured.' });
    return;
  }
  if (backendOrigin.protocol !== 'https:' && backendOrigin.hostname !== 'localhost' && backendOrigin.hostname !== '127.0.0.1') {
    response.status(503).json({ detail: 'The advisory service is not configured.' });
    return;
  }

  const incoming = new URL(request.url, 'http://vercel.local');
  if (!incoming.pathname.startsWith('/api/')) {
    response.status(404).end();
    return;
  }

  const destination = new URL(`${incoming.pathname}${incoming.search}`, backendOrigin);
  const headers = new Headers();
  for (const name of FORWARDED_HEADERS) {
    const value = request.headers[name];
    if (value) headers.set(name, value);
  }

  let body;
  if (!['GET', 'HEAD'].includes(request.method)) {
    body = typeof request.body === 'string' ? request.body : JSON.stringify(request.body ?? {});
  }

  try {
    const upstream = await fetch(destination, {
      method: request.method,
      headers,
      body,
      redirect: 'manual',
    });
    response.status(upstream.status);
    for (const name of ['content-type', 'cache-control']) {
      const value = upstream.headers.get(name);
      if (value) response.setHeader(name, value);
    }
    const cookies = upstream.headers.getSetCookie?.();
    if (cookies?.length) response.setHeader('set-cookie', cookies);
    const payload = Buffer.from(await upstream.arrayBuffer());
    response.end(payload);
  } catch {
    response.status(502).json({ detail: 'Could not reach the advisory service.' });
  }
}
