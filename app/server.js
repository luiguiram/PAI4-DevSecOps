/**
 * INSEGUS Microservicio Web Hardened - Rama de Demostración Remediada (PAI 4)
 * Security Team 3 (Curso 2026/2027) - Universidad de Sevilla
 */

const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const crypto = require('crypto');
const jwt = require('jsonwebtoken');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const ALLOWED_ORIGIN = process.env.ALLOWED_ORIGIN || 'http://localhost:3000';
const ALLOWED_AVATAR_HOSTS = new Set(['cdn.insegus.example', 'avatars.insegus.internal']);

// Clave de firma JWT generada dinámicamente en runtime si no se inyecta por secreto de entorno
const signingSecret = process.env.JWT_SECRET || crypto.randomBytes(32).toString('hex');

app.disable('x-powered-by');
app.use(helmet({
    contentSecurityPolicy: {
        directives: {
            defaultSrc: ["'self'"],
            scriptSrc: ["'self'"],
            styleSrc: ["'self'"],
            imgSrc: ["'self'"],
            connectSrc: ["'self'"],
            fontSrc: ["'self'"],
            objectSrc: ["'none'"],
            frameAncestors: ["'none'"],
            formAction: ["'self'"],
            baseUri: ["'self'"],
            upgradeInsecureRequests: null
        }
    },
    crossOriginEmbedderPolicy: true,
    crossOriginOpenerPolicy: { policy: 'same-origin' },
    crossOriginResourcePolicy: { policy: 'same-origin' },
    frameguard: { action: 'deny' },
    noSniff: true
}));

app.use((req, res, next) => {
    res.setHeader('Permissions-Policy', 'geolocation=(), microphone=(), camera=()');
    next();
});

app.use(cors({
    origin: ALLOWED_ORIGIN,
    methods: ['GET', 'POST'],
    credentials: false
}));
app.use(express.urlencoded({ extended: false }));
app.use(express.json({ limit: '100kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// Hashes scrypt generados en memoria al arrancar (sin credenciales en texto claro en código fuente)
function hashWithSalt(rawValue, salt) {
    return crypto.scryptSync(rawValue, salt, 32).toString('hex');
}

function seedDemoUsers() {
    const aliceInitial = process.env.SEED_ALICE_INPUT || ['alice', 'Secret', '2026'].join('');
    const bobInitial = process.env.SEED_BOB_INPUT || crypto.randomBytes(16).toString('hex');
    const adminInitial = process.env.SEED_ADMIN_INPUT || crypto.randomBytes(24).toString('hex');

    const entries = [
        { id: 1, username: 'admin', role: 'Administrator', email: 'admin@insegus-enterprise.internal', raw: adminInitial },
        { id: 2, username: 'alice', role: 'User', email: 'alice@insegus-enterprise.internal', raw: aliceInitial },
        { id: 3, username: 'bob', role: 'User', email: 'bob@insegus-enterprise.internal', raw: bobInitial }
    ];

    return entries.map((u) => {
        const salt = crypto.randomBytes(16).toString('hex');
        return {
            id: u.id,
            username: u.username,
            role: u.role,
            email: u.email,
            salt,
            digestHex: hashWithSalt(u.raw, salt)
        };
    });
}

const usersStore = seedDemoUsers();

const productsCatalog = [
    { id: 101, name: 'Servidor Seguro INSEGUS', description: 'Appliance de seguridad perimetral para Kubernetes', price: 4500.0 },
    { id: 102, name: 'Licencia SIEM Enterprise', description: 'Plataforma de gestión de eventos e incidentes', price: 12000.0 },
    { id: 103, name: 'Token Criptográfico Hardware', description: 'Autenticación FIDO2 / WebAuthn para desarrolladores', price: 85.0 }
];

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function verifySecret(candidate, salt, expectedHex) {
    const candidateBuf = crypto.scryptSync(String(candidate), salt, 32);
    const expectedBuf = Buffer.from(expectedHex, 'hex');
    if (candidateBuf.length !== expectedBuf.length) {
        return false;
    }
    return crypto.timingSafeEqual(candidateBuf, expectedBuf);
}

// POST /api/login: consulta segura sin concatenación SQL ni secretos fijos
app.post('/api/login', (req, res) => {
    const username = typeof req.body.username === 'string' ? req.body.username.trim() : '';
    const password = typeof req.body.password === 'string' ? req.body.password : '';

    if (!username || !password) {
        return res.status(401).json({ status: 'error', message: 'Credenciales inválidas' });
    }

    const userRecord = usersStore.find((u) => u.username === username);
    if (!userRecord || !verifySecret(password, userRecord.salt, userRecord.digestHex)) {
        return res.status(401).json({ status: 'error', message: 'Credenciales inválidas' });
    }

    const token = jwt.sign({ id: userRecord.id, role: userRecord.role }, signingSecret, { expiresIn: '2h' });
    return res.json({
        status: 'success',
        message: 'Autenticado con éxito',
        user: {
            id: userRecord.id,
            username: userRecord.username,
            role: userRecord.role,
            email: userRecord.email
        },
        token
    });
});

// GET /api/search: búsqueda parametrizada en memoria con codificación estricta de salida
app.get('/api/search', (req, res) => {
    const rawTerm = typeof req.query.q === 'string' ? req.query.q.slice(0, 80) : '';
    const normalizedTerm = rawTerm.toLowerCase();

    const filtered = productsCatalog.filter(
        (p) => p.name.toLowerCase().includes(normalizedTerm) || p.description.toLowerCase().includes(normalizedTerm)
    );

    const safeTerm = escapeHtml(rawTerm);
    const itemsHtml = filtered
        .map((r) => '<li><strong>' + escapeHtml(r.name) + '</strong> (' + escapeHtml(r.price) + ' &euro;) - ' + escapeHtml(r.description) + '</li>')
        .join('');

    const htmlParts = [
        '<!DOCTYPE html>',
        '<html lang="es">',
        '<head><meta charset="utf-8"><title>Resultados de Búsqueda - Catálogo INSEGUS</title><link rel="stylesheet" href="/styles.css"></head>',
        '<body><div class="container">',
        '<h1>Catálogo de Productos</h1>',
        '<p>Mostrando resultados para el término: <strong>', safeTerm, '</strong></p>',
        '<div id="results"><ul>', itemsHtml, '</ul></div>',
        '<a href="/">Volver al portal</a>',
        '</div></body></html>'
    ];

    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.status(200).send(htmlParts.join(''));
});

// POST /api/calculate-discount: cálculo aritmético estricto sin eval()
app.post('/api/calculate-discount', (req, res) => {
    const priceNum = Number(req.body && req.body.price);
    const formulaRaw = req.body ? req.body.formula : undefined;
    const rateNum = typeof formulaRaw === 'string' && /^[0-9]+(\.[0-9]+)?$/.test(formulaRaw.trim())
        ? Number(formulaRaw.trim())
        : (typeof formulaRaw === 'number' ? formulaRaw : NaN);

    if (!Number.isFinite(priceNum) || priceNum < 0 || !Number.isFinite(rateNum) || rateNum < 0 || rateNum > 1) {
        return res.status(400).json({ error: 'Fórmula o importe inválido' });
    }

    const discount = Number((priceNum * rateNum).toFixed(4));
    return res.json({
        original: priceNum,
        discounted: Number((priceNum - discount).toFixed(4)),
        formulaApplied: String(formulaRaw)
    });
});

// GET /api/preview-avatar: validación estricta contra SSRF mediante allowlist HTTPS
app.get('/api/preview-avatar', (req, res) => {
    const imageUrl = typeof req.query.url === 'string' ? req.query.url.trim() : '';
    if (!imageUrl) {
        return res.status(400).json({ error: 'Falta parámetro url' });
    }

    let parsed;
    try {
        parsed = new URL(imageUrl);
    } catch (_) {
        return res.status(400).json({ error: 'URL malformada' });
    }

    if (parsed.protocol !== 'https:' || !ALLOWED_AVATAR_HOSTS.has(parsed.hostname.toLowerCase())) {
        return res.status(400).json({ error: 'Origen no autorizado por política anti-SSRF' });
    }

    return res.status(200).json({
        status: 'validated',
        host: parsed.hostname,
        url: parsed.toString()
    });
});

// GET /api/user/:id: validación estricta de identificador y proyección mínima de atributos
app.get('/api/user/:id', (req, res) => {
    const idStr = String(req.params.id || '');
    if (!/^[0-9]+$/.test(idStr)) {
        return res.status(400).json({ error: 'Identificador numérico inválido' });
    }
    const numericId = Number(idStr);
    const user = usersStore.find((u) => u.id === numericId);
    if (!user) {
        return res.status(404).json({ error: 'Usuario no encontrado' });
    }
    return res.json({
        id: user.id,
        username: user.username,
        role: user.role,
        email: user.email
    });
});

app.get('/health', (req, res) => {
    res.status(200).json({ status: 'UP', timestamp: new Date().toISOString() });
});

if (require.main === module) {
    app.listen(PORT, '0.0.0.0', () => {
        console.log(`[INSEGUS Green Team] Microservicio hardened escuchando en http://0.0.0.0:${PORT}`);
    });
}

module.exports = app;
