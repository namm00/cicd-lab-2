// A small static server and /api proxy. No build happens at runtime.
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';

const root = resolve('dist');
const backend = new URL(process.env.BACKEND_URL ?? 'http://backend:8000');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.ico': 'image/x-icon' };

http.createServer(async (request, response) => {
  if (request.url === '/api' || request.url.startsWith('/api/')) {
    const upstream = http.request({
      hostname: backend.hostname, port: backend.port, path: request.url,
      method: request.method, headers: { ...request.headers, host: backend.host },
    }, (incoming) => {
      response.writeHead(incoming.statusCode, incoming.headers);
      incoming.pipe(response);
      incoming.on('error', () => response.destroy());
    });
    upstream.setTimeout(10000, () => upstream.destroy(new Error('Backend timeout')));
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'application/json' });
      response.end(JSON.stringify({ detail: 'Backend unavailable' }));
    });
    request.on('aborted', () => upstream.destroy());
    request.pipe(upstream);
    return;
  }
  if (!['GET', 'HEAD'].includes(request.method)) {
    response.writeHead(405); response.end(); return;
  }
  try {
    const path = decodeURIComponent(new URL(request.url, 'http://frontend').pathname);
    const file = resolve(root, '.' + (path === '/' ? '/index.html' : path));
    if (!file.startsWith(root + '/')) { response.writeHead(403); response.end(); return; }
    const body = await readFile(file);
    response.writeHead(200, {
      'Content-Type': types[extname(file)] ?? 'application/octet-stream',
      'Cache-Control': path.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
    });
    response.end(request.method === 'HEAD' ? undefined : body);
  } catch {
    response.writeHead(404); response.end('Not found');
  }
}).listen(8080, '0.0.0.0', () => console.log('Frontend listening on :8080'));
