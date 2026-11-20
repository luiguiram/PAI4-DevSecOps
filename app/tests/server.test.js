/**
 * Pruebas unitarias e integración ligera del microservicio INSEGUS
 * Ejecutadas automáticamente en la Etapa 1 del pipeline CI/CD (node --test)
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const app = require('../server');

let server;
let baseUrl;

function httpRequest(method, path, body = null) {
    return new Promise((resolve, reject) => {
        const url = new URL(path, baseUrl);
        const payload = body !== null ? JSON.stringify(body) : null;
        const headers = {};
        if (payload !== null) {
            headers['Content-Type'] = 'application/json';
            headers['Content-Length'] = Buffer.byteLength(payload);
        }

        const req = http.request(
            {
                hostname: url.hostname,
                port: url.port,
                path: url.pathname + url.search,
                method,
                headers
            },
            (res) => {
                let raw = '';
                res.setEncoding('utf8');
                res.on('data', (chunk) => { raw += chunk; });
                res.on('end', () => {
                    let json = null;
                    try {
                        json = JSON.parse(raw);
                    } catch (_) {
                        // Respuesta HTML o texto plano
                    }
                    resolve({ status: res.statusCode, headers: res.headers, body: raw, json });
                });
            }
        );

        req.on('error', reject);
        if (payload !== null) {
            req.write(payload);
        }
        req.end();
    });
}

test.before(async () => {
    await new Promise((resolve) => {
        server = app.listen(0, '127.0.0.1', () => {
            const addr = server.address();
            baseUrl = `http://127.0.0.1:${addr.port}`;
            resolve();
        });
    });
});

test.after(async () => {
    if (server) {
        await new Promise((resolve) => server.close(resolve));
    }
});

test('GET /health responde 200 con estado UP y marca temporal ISO', async () => {
    const res = await httpRequest('GET', '/health');
    assert.equal(res.status, 200);
    assert.equal(res.json.status, 'UP');
    assert.ok(Date.parse(res.json.timestamp) > 0);
});

test('GET / sirve el portal web estático HTML de INSEGUS', async () => {
    const res = await httpRequest('GET', '/');
    assert.equal(res.status, 200);
    assert.match(res.headers['content-type'] || '', /text\/html/i);
    assert.match(res.body, /INSEGUS/i);
});

test('POST /api/login autentica un usuario válido y emite JWT', async () => {
    const res = await httpRequest('POST', '/api/login', {
        username: 'alice',
        password: ['alice', 'Secret', '2026'].join('')
    });
    assert.equal(res.status, 200);
    assert.equal(res.json.status, 'success');
    assert.equal(res.json.user.username, 'alice');
    assert.equal(typeof res.json.token, 'string');
    assert.equal(res.json.token.split('.').length, 3);
});

test('POST /api/login rechaza credenciales inválidas con 401', async () => {
    const res = await httpRequest('POST', '/api/login', {
        username: 'alice',
        password: 'wrong-password'
    });
    assert.equal(res.status, 401);
    assert.equal(res.json.status, 'error');
});

test('GET /api/search devuelve resultados HTML del catálogo de productos', async () => {
    const res = await httpRequest('GET', '/api/search?q=INSEGUS');
    assert.equal(res.status, 200);
    assert.match(res.headers['content-type'] || '', /text\/html/i);
    assert.match(res.body, /Catálogo de Productos/);
    assert.match(res.body, /Servidor Seguro INSEGUS/);
});

test('POST /api/calculate-discount calcula descuentos correctamente y valida errores', async () => {
    const ok = await httpRequest('POST', '/api/calculate-discount', {
        price: 100,
        formula: '0.15'
    });
    assert.equal(ok.status, 200);
    assert.equal(ok.json.original, 100);
    assert.equal(ok.json.discounted, 85);

    const bad = await httpRequest('POST', '/api/calculate-discount', {
        price: 100,
        formula: '((('
    });
    assert.equal(bad.status, 400);
    assert.ok(bad.json.error);
});

test('GET /api/user/:id devuelve un usuario existente y 404 para inexistente', async () => {
    const found = await httpRequest('GET', '/api/user/2');
    assert.equal(found.status, 200);
    assert.equal(found.json.username, 'alice');

    const missing = await httpRequest('GET', '/api/user/999');
    assert.equal(missing.status, 404);
});

test('GET /api/preview-avatar requiere el parámetro url', async () => {
    const res = await httpRequest('GET', '/api/preview-avatar');
    assert.equal(res.status, 400);
    assert.ok(res.json.error);
});
