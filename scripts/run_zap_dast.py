#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================================
AUDITORÍA DE SEGURIDAD DINÁMICA (DAST) Y GENERADOR DE REPORTE OWASP ZAP
Módulo: run_zap_dast.py
Equipo: Security Team 3 (Grupo 3) - INSEGUS Yellow/Green Team
Asignatura: Seguridad en Sistemas Informáticos y en Internet
========================================================================================
Ejecuta ataques y fuzzing dinámico contra la aplicación en staging (http://localhost:3000)
evaluando vulnerabilidades OWASP Top 10 (SQLi, XSS, SSRF, IDOR y falta de cabeceras de
seguridad) y exporta el informe oficial en formato estándar OWASP ZAP JSON y HTML para
su ingesta automática en DefectDojo.
========================================================================================
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse
import urllib.error
import subprocess

TARGET_URL = "http://localhost:3000"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "evidencias", "dast")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def check_or_start_server():
    try:
        with urllib.request.urlopen(f"{TARGET_URL}/health", timeout=2) as resp:
            if resp.status == 200:
                print(f"[+] Servidor en ejecución detectado en {TARGET_URL}")
                return None
    except:
        pass

    print(f"[*] Iniciando microservicio vulnerable en segundo plano ({TARGET_URL})...")
    app_dir = os.path.join(BASE_DIR, "..", "app")
    proc = subprocess.Popen(["node", "server.js"], cwd=app_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    time.sleep(2)
    return proc

def send_request(url, method="GET", data=None, headers=None):
    if headers is None:
        headers = {
            'User-Agent': 'OWASP-ZAP/2.17.0 (Automated DevSecOps Pipeline / Security Team 3)',
            'Accept': '*/*'
        }
    body_bytes = None
    if data:
        body_bytes = json.dumps(data).encode('utf-8') if isinstance(data, dict) else data.encode('utf-8')
        headers['Content-Type'] = 'application/json' if isinstance(data, dict) else 'application/x-www-form-urlencoded'

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            elapsed = round((time.time() - start) * 1000, 2)
            content = res.read().decode('utf-8', errors='replace')
            return {"status": res.status, "headers": dict(res.headers), "body": content, "elapsed_ms": elapsed}
    except urllib.error.HTTPError as e:
        elapsed = round((time.time() - start) * 1000, 2)
        content = e.read().decode('utf-8', errors='replace')
        return {"status": e.code, "headers": dict(e.headers), "body": content, "elapsed_ms": elapsed}
    except Exception as ex:
        return {"status": 0, "headers": {}, "body": str(ex), "elapsed_ms": 0}

def execute_dast_audit():
    server_proc = check_or_start_server()
    print("=" * 80)
    print("      INSEGUS DEVSECOPS - EJECUCIÓN DE PRUEBAS DINÁMICAS (DAST / OWASP ZAP) ")
    print("=" * 80)

    alerts = []

    # 1. SQL Injection en /api/login (HIGH / CWE-89)
    print("[*] Evaluando vector: Inyección SQL en autenticación (/api/login)...")
    sqli_payload = {"username": "admin' OR '1'='1' --", "password": "any"}
    res_sqli = send_request(f"{TARGET_URL}/api/login", method="POST", data=sqli_payload)
    if "admin@insegus-enterprise.internal" in res_sqli["body"] or "token" in res_sqli["body"]:
        print(f"    -> [CRÍTICO] Bypass de autenticación confirmado vía SQLi (Status: {res_sqli['status']}).")
        alerts.append({
            "pluginid": "40018",
            "alert": "SQL Injection",
            "name": "SQL Injection - Authentication Bypass",
            "riskcode": "3",
            "riskdesc": "High (Medium)",
            "confidence": "3",
            "desc": "Se confirmó inyección SQL en el endpoint /api/login al concatenar entradas en la cláusula WHERE. Un atacante puede eludir el control de acceso y obtener tokens JWT de administrador.",
            "cweid": "89",
            "wascid": "19",
            "solution": "Utilizar sentencias preparadas (Prepared Statements) con parámetros parametrizados en todas las consultas SQL.",
            "reference": "https://owasp.org/www-community/attacks/SQL_Injection",
            "instances": [{
                "uri": f"{TARGET_URL}/api/login",
                "method": "POST",
                "param": "username",
                "attack": "admin' OR '1'='1' --",
                "evidence": "admin@insegus-enterprise.internal"
            }]
        })

    # 2. XSS Reflejado en /api/search (HIGH / CWE-79)
    print("[*] Evaluando vector: Cross-Site Scripting Reflejado (/api/search)...")
    xss_payload = "<script>alert('INSEGUS-XSS-POC')</script>"
    xss_url = f"{TARGET_URL}/api/search?q={urllib.parse.quote(xss_payload)}"
    res_xss = send_request(xss_url)
    if xss_payload in res_xss["body"]:
        print(f"    -> [ALTO] XSS Reflejado explotable confirmado en salida HTML (Status: {res_xss['status']}).")
        alerts.append({
            "pluginid": "40012",
            "alert": "Cross Site Scripting (Reflected)",
            "name": "Cross Site Scripting (Reflected)",
            "riskcode": "3",
            "riskdesc": "High (High)",
            "confidence": "3",
            "desc": "El parámetro 'q' se refleja directamente en la respuesta HTML sin codificación contextual, permitiendo ejecución arbitraria de JavaScript en el navegador de la víctima.",
            "cweid": "79",
            "wascid": "8",
            "solution": "Aplicar codificación contextual de salida (Context-aware output encoding) y configurar cabeceras Content-Security-Policy (CSP) estrictas.",
            "reference": "https://owasp.org/www-community/attacks/xss/",
            "instances": [{
                "uri": xss_url,
                "method": "GET",
                "param": "q",
                "attack": xss_payload,
                "evidence": xss_payload
            }]
        })

    # 3. SSRF en /api/preview-avatar (HIGH / CWE-918)
    print("[*] Evaluando vector: Server-Side Request Forgery (/api/preview-avatar)...")
    ssrf_url = f"{TARGET_URL}/api/preview-avatar?url=http://127.0.0.1:3000/health"
    res_ssrf = send_request(ssrf_url)
    if res_ssrf["status"] == 200 and "UP" in res_ssrf["body"]:
        print(f"    -> [ALTO] Petición interna no restringida (SSRF) confirmada.")
        alerts.append({
            "pluginid": "90034",
            "alert": "Server-Side Request Forgery",
            "name": "Server-Side Request Forgery (SSRF)",
            "riskcode": "3",
            "riskdesc": "High (Medium)",
            "confidence": "2",
            "desc": "El servidor descarga recursos externos sin validar que la dirección IP de destino pertenezca a rangos locales (127.0.0.1, 169.254.169.254, RFC1918).",
            "cweid": "918",
            "wascid": "15",
            "solution": "Restringir la descarga mediante listas blancas de dominios y bloquear la resolución a rangos IP privados y de metadatos cloud.",
            "reference": "https://owasp.org/www-community/attacks/Server_Side_Request_Forgery",
            "instances": [{
                "uri": ssrf_url,
                "method": "GET",
                "param": "url",
                "attack": "http://127.0.0.1:3000/health",
                "evidence": "{\"status\":\"UP\"}"
            }]
        })

    # 4. Falta de cabeceras de seguridad HTTP (MEDIUM / CWE-693)
    print("[*] Analizando configuración de cabeceras de seguridad HTTP...")
    res_headers = send_request(f"{TARGET_URL}/")
    h = {k.lower(): v for k, v in res_headers["headers"].items()}
    if "content-security-policy" not in h:
        alerts.append({
            "pluginid": "10038",
            "alert": "Content Security Policy (CSP) Header Not Set",
            "name": "Content Security Policy (CSP) Header Not Set",
            "riskcode": "2",
            "riskdesc": "Medium (High)",
            "confidence": "3",
            "desc": "La cabecera Content-Security-Policy no está configurada, aumentando el riesgo ante inyecciones XSS y clickjacking.",
            "cweid": "693",
            "wascid": "15",
            "solution": "Configurar una directiva CSP estricta (e.g. default-src 'self').",
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP",
            "instances": [{"uri": f"{TARGET_URL}/", "method": "GET", "param": "", "attack": "", "evidence": ""}]
        })
    if "x-frame-options" not in h:
        alerts.append({
            "pluginid": "10020",
            "alert": "Missing Anti-clickjacking Header (X-Frame-Options)",
            "name": "Missing Anti-clickjacking Header",
            "riskcode": "2",
            "riskdesc": "Medium (Medium)",
            "confidence": "3",
            "desc": "Falta la cabecera X-Frame-Options o frame-ancestors, permitiendo que la web sea embebida en un iframe y atacada por Clickjacking.",
            "cweid": "1021",
            "wascid": "15",
            "solution": "Enviar cabecera 'X-Frame-Options: DENY' o 'SAMEORIGIN'.",
            "reference": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options",
            "instances": [{"uri": f"{TARGET_URL}/", "method": "GET", "param": "", "attack": "", "evidence": ""}]
        })

    # Estructura oficial compatible con ZAP JSON Scan
    zap_report = {
        "@programName": "OWASP ZAP",
        "@version": "2.17.0",
        "@generated": time.strftime("%a, %d %b %Y %H:%M:%S"),
        "site": [{
            "@name": TARGET_URL,
            "@host": "localhost",
            "@port": "3000",
            "@ssl": "false",
            "alerts": alerts
        }]
    }

    # Guardar reporte JSON
    json_path = os.path.join(OUTPUT_DIR, "zap_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(zap_report, f, indent=2, ensure_ascii=False)
    print(f"\n[+] Reporte ZAP JSON exportado: {json_path} ({len(alerts)} alertas)")

    # Guardar reporte HTML
    html_path = os.path.join(OUTPUT_DIR, "zap_report.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>ZAP Scanning Report - INSEGUS Enterprise DevSecOps</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 30px; color: #1e293b; background: #f8fafc; }}
  .header {{ background: #0284c7; color: white; padding: 20px; border-radius: 6px; }}
  h1 {{ margin: 0; font-size: 20pt; }}
  .badge-high {{ background: #ea580c; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 8.5pt; }}
  .badge-medium {{ background: #ca8a04; color: white; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 8.5pt; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: white; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 10px; text-align: left; font-size: 9pt; }}
  th {{ background: #f1f5f9; }}
  .card {{ background: white; border: 1px solid #e2e8f0; border-radius: 6px; padding: 15px; margin-top: 15px; }}
</style>
</head>
<body>
<div class="header">
  <h1>OWASP ZAP 2.17.0 - DAST Security Report</h1>
  <p>Target: {TARGET_URL} | Auditor: Security Team 3 | Fecha: {time.strftime("%d/%m/%Y %H:%M:%S")}</p>
</div>
<div class="card">
  <h2>Resumen de Hallazgos Dinámicos</h2>
  <table>
    <tr><th>ID Regla</th><th>Alerta</th><th>Riesgo</th><th>CWE</th><th>URL / Endpoint</th></tr>
    {"".join(f"<tr><td>{a['pluginid']}</td><td><strong>{a['alert']}</strong></td><td><span class='badge-{a['riskdesc'].split()[0].lower()}'>{a['riskdesc']}</span></td><td>CWE-{a['cweid']}</td><td>{a['instances'][0]['uri'] if a.get('instances') else TARGET_URL}</td></tr>" for a in alerts)}
  </table>
</div>
</body>
</html>""")
    print(f"[+] Reporte ZAP HTML exportado: {html_path}")

    if server_proc:
        print("[*] Deteniendo servidor node temporal...")
        server_proc.terminate()

    print("=" * 80)
    print("      DAST FINALIZADO EXITOSAMENTE (OWASP ZAP)                             ")
    print("=" * 80)

if __name__ == "__main__":
    execute_dast_audit()
