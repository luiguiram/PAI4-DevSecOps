/**
 * INSEGUS Microservicio Web Vulnerable - Aplicación de Prueba PAI 4
 * Security Team 3 (Curso 2026/2027) - Universidad de Sevilla
 *
 * NOTA: Esta aplicación contiene vulnerabilidades intencionadas con fines educativos
 */

const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const jwt = require('jsonwebtoken');
const axios = require('axios');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// ============================================================================
// VULNERABILIDAD SAST #1 (CWE-798): Credenciales y secretos hardcodeados
// ============================================================================
const JWT_SECRET = "INSEGUS_HARDCODED_JWT_SECRET_KEY_PROD_2026!";
const DB_ADMIN_PASS = "admin1234_hardcoded_insegus_master_pass";
const AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE";
const AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY";

// Configuración insegura de CORS (CWE-942)
app.use(cors({ origin: '*' }));
app.use(bodyParser.urlencoded({ extended: true }));
app.use(bodyParser.json());
app.use(express.static(path.join(__dirname, 'public')));

// Base de datos de prueba en memoria (con fallback transparente para Node moderno)
const mockUsers = [
    { id: 1, username: "admin", password: "admin1234_hardcoded_insegus_master_pass", role: "Administrator", email: "admin@insegus-enterprise.internal" },
    { id: 2, username: "alice", password: "aliceSecret2026", role: "User", email: "alice@insegus-enterprise.internal" },
    { id: 3, username: "bob", password: "bobP@ssw0rd", role: "User", email: "bob@insegus-enterprise.internal" }
];

const mockProducts = [
    { id: 101, name: "Servidor Seguro INSEGUS", description: "Appliance de seguridad perimetral para Kubernetes", price: 4500.0 },
    { id: 102, name: "Licencia SIEM Enterprise", description: "Plataforma de gestión de eventos e incidentes", price: 12000.0 },
    { id: 103, name: "Token Criptográfico Hardware", description: "Autenticación FIDO2 / WebAuthn para desarrolladores", price: 85.0 }
];

let db;
try {
    const sqlite3 = require('sqlite3').verbose();
    db = new sqlite3.Database(':memory:');
    db.serialize(() => {
        db.run("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, role TEXT, email TEXT)");
        db.run("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, description TEXT, price REAL)");
        const stmtUser = db.prepare("INSERT INTO users VALUES (?, ?, ?, ?, ?)");
        mockUsers.forEach(u => stmtUser.run(u.id, u.username, u.password, u.role, u.email));
        stmtUser.finalize();
        const stmtProd = db.prepare("INSERT INTO products VALUES (?, ?, ?, ?)");
        mockProducts.forEach(p => stmtProd.run(p.id, p.name, p.description, p.price));
        stmtProd.finalize();
    });
} catch (e) {
    console.log("[i] Usando driver SQL en memoria con soporte de inyección dinámico");
    db = {
        get: (query, params, cb) => {
            if (typeof params === 'function') { cb = params; params = []; }
            const q = query.toLowerCase();
            if (q.includes("or '1'='1") || q.includes("or 1=1") || q.includes("admin'")) {
                return cb(null, mockUsers[0]);
            }
            if (params && params.length > 0) {
                const u = mockUsers.find(x => x.id == params[0]);
                return cb(null, u);
            }
            const match = mockUsers.find(x => query.includes(`'${x.username}'`) && query.includes(`'${x.password}'`));
            return cb(null, match);
        },
        all: (query, params, cb) => {
            if (typeof params === 'function') { cb = params; params = []; }
            return cb(null, mockProducts);
        }
    };
}

// ============================================================================
// VULNERABILIDAD DAST/SAST #2 (CWE-89): Inyección SQL directa sin parametrizar
// ============================================================================
app.post('/api/login', (req, res) => {
    const username = req.body.username || '';
    const password = req.body.password || '';
    // Concatenación directa de strings en consulta SQL: vulnerable a SQLi
    const query = `SELECT id, username, role, email FROM users WHERE username = '${username}' AND password = '${password}'`;

    console.log(`[SQL EXEC] ${query}`);

    db.get(query, (err, row) => {
        if (err) {
            return res.status(500).json({ error: "Database error", details: err.message });
        }
        if (row) {
            const token = jwt.sign({ id: row.id, role: row.role }, JWT_SECRET, { expiresIn: '2h' });
            return res.json({ status: "success", message: "Autenticado con éxito", user: row, token });
        } else {
            return res.status(401).json({ status: "error", message: "Credenciales inválidas" });
        }
    });
});

// ============================================================================
// VULNERABILIDAD DAST/SAST #3 (CWE-79): Cross-Site Scripting (XSS Reflejado)
// ============================================================================
app.get('/api/search', (req, res) => {
    const queryTerm = req.query.q || '';
    
    // Inyección SQL adicional en catálogo
    const sql = `SELECT * FROM products WHERE name LIKE '%${queryTerm}%' OR description LIKE '%${queryTerm}%'`;
    
    db.all(sql, (err, rows) => {
        if (err) {
            return res.status(500).send(`<h3>Error de base de datos:</h3><pre>${err.message}</pre>`);
        }
        // XSS Reflejado: Renderizado directo de entrada no sanitizada en HTML
        const html = `
            <html>
            <head><title>Resultados de Búsqueda - Catálogo INSEGUS</title></head>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h1>Catálogo de Productos</h1>
                <p>Mostrando resultados para el término: <strong>${queryTerm}</strong></p>
                <div id="results">
                    <ul>
                        ${rows.map(r => `<li><strong>${r.name}</strong> (${r.price} €) - ${r.description}</li>`).join('')}
                    </ul>
                </div>
                <a href="/">Volver al portal</a>
            </body>
            </html>
        `;
        res.setHeader('Content-Type', 'text/html');
        return res.send(html);
    });
});

// ============================================================================
// VULNERABILIDAD SAST #4 (CWE-95): Eval injection / Deserialización insegura
// ============================================================================
app.post('/api/calculate-discount', (req, res) => {
    const { formula, price } = req.body;
    try {
        // Uso peligroso de eval() sobre input de usuario
        const discount = eval(`(${price}) * (${formula})`);
        res.json({ original: price, discounted: price - discount, formulaApplied: formula });
    } catch (e) {
        res.status(400).json({ error: "Fórmula inválida", details: e.message });
    }
});

// ============================================================================
// VULNERABILIDAD DAST/SAST #5 (CWE-918): Server-Side Request Forgery (SSRF)
// ============================================================================
app.get('/api/preview-avatar', async (req, res) => {
    const imageUrl = req.query.url;
    if (!imageUrl) {
        return res.status(400).json({ error: "Falta parámetro url" });
    }
    try {
        // Petición HTTP saliente sin validar host ni rangos IP internos
        const response = await axios.get(imageUrl, { timeout: 3000, responseType: 'arraybuffer' });
        res.set('Content-Type', response.headers['content-type'] || 'image/png');
        return res.send(response.data);
    } catch (err) {
        return res.status(502).json({ error: "Error al descargar recurso", details: err.message });
    }
});

// ============================================================================
// VULNERABILIDAD DAST/SAST #6 (CWE-639): Control de acceso roto / IDOR
// ============================================================================
app.get('/api/user/:id', (req, res) => {
    const userId = req.params.id;
    // Sin comprobación de sesión o autorización basada en roles
    db.get("SELECT id, username, role, email FROM users WHERE id = ?", [userId], (err, row) => {
        if (err) return res.status(500).json({ error: err.message });
        if (!row) return res.status(404).json({ error: "Usuario no encontrado" });
        return res.json(row);
    });
});

// Endpoint de health check para Kubernetes y pipeline
app.get('/health', (req, res) => {
    res.status(200).json({ status: "UP", timestamp: new Date().toISOString() });
});

// Iniciar servidor
if (require.main === module) {
    app.listen(PORT, '0.0.0.0', () => {
        console.log(`[INSEGUS Yellow Team] Microservicio vulnerable escuchando en http://0.0.0.0:${PORT}`);
    });
}

module.exports = app;
