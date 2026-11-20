#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================================
CLIENTE DE INTEGRACIÓN DEFECTDOJO API V2 - PAI 4 DEVSECOPS
Módulo: defectdojo_client.py
Equipo: Security Team 3 (Grupo 3) - INSEGUS Yellow/Green Team
Asignatura: Seguridad en Sistemas Informáticos y en Internet
========================================================================================
Interactúa con la API REST v2 de OWASP DefectDojo usando DEFECTDOJO_URL y
DEFECTDOJO_API_KEY (inyectadas vía GitHub Actions Secrets):
1. Busca o crea el Producto ('INSEGUS Web Application') y el Engagement CI/CD.
2. Importa automáticamente los informes de Semgrep (SAST), Trivy (SCA & IaC) y ZAP (DAST)
   mediante multipart/form-data a POST /api/v2/import-scan/.
3. Ejecuta el triaje técnico automatizado vía PATCH /api/v2/findings/{id}/ y documenta
   falsos positivos justificados vía POST /api/v2/findings/{id}/notes/.
4. Exporta el resumen consolidado de métricas y hallazgos en formato JSON.

Si DEFECTDOJO_URL o DEFECTDOJO_API_KEY no están definidas (o la instancia remota no es
accesible y no se pasa --strict-api), conmuta de forma transparente al backend local
compatible (mock_defectdojo.py) para garantizar reproducibilidad offline.
========================================================================================
"""

import os
import sys
import json
import uuid
import time
import argparse
import datetime
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)
from mock_defectdojo import DefectDojoDatabase

CORS_FP_REASON = (
    "El endpoint expone únicamente recursos estáticos y APIs públicas de prueba en red "
    "interna aislada (Kubernetes ClusterIP). Se valida que el servicio no maneja cookies "
    "de sesión cruzadas (autenticación vía Bearer JWT)."
)

DEBUG_MITIGATED_NOTE = (
    "Corregido en manifiesto de producción mediante inyección de variable "
    "NODE_ENV=production vía Kubernetes Secret."
)


def _zap_json_to_xml_bytes(zap_data: Dict[str, Any]) -> bytes:
    """Convierte un informe OWASP ZAP JSON al formato OWASPZAPReport XML requerido por DefectDojo."""
    root = ET.Element(
        "OWASPZAPReport",
        attrib={
            "version": str(zap_data.get("@version", "2.17.0")),
            "generated": str(zap_data.get("@generated", time.strftime("%a, %d %b %Y %H:%M:%S"))),
        },
    )
    for site in zap_data.get("site", []):
        site_el = ET.SubElement(
            root,
            "site",
            attrib={
                "name": str(site.get("@name", "http://localhost:3000")),
                "host": str(site.get("@host", "localhost")),
                "port": str(site.get("@port", "3000")),
                "ssl": str(site.get("@ssl", "false")),
            },
        )
        alerts_el = ET.SubElement(site_el, "alerts")
        for alert in site.get("alerts", []):
            item = ET.SubElement(alerts_el, "alertitem")
            for tag in (
                "pluginid",
                "alert",
                "name",
                "riskcode",
                "confidence",
                "riskdesc",
                "desc",
                "solution",
                "reference",
                "cweid",
                "wascid",
            ):
                child = ET.SubElement(item, tag)
                child.text = str(alert.get(tag, ""))

            instances = alert.get("instances", [])
            ET.SubElement(item, "count").text = str(len(instances) or 1)
            instances_el = ET.SubElement(item, "instances")
            for inst in instances:
                inst_el = ET.SubElement(instances_el, "instance")
                for field in ("uri", "method", "param", "attack", "evidence"):
                    if field in inst:
                        el = ET.SubElement(inst_el, field)
                        el.text = str(inst.get(field, ""))

    return b'<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="utf-8")


def _encode_multipart_formdata(
    fields: Dict[str, str],
    file_field: str,
    filename: str,
    file_bytes: bytes,
    content_type: str = "application/json",
) -> Tuple[bytes, str]:
    """Construye un cuerpo HTTP multipart/form-data compatible con /api/v2/import-scan/."""
    boundary = f"----DefectDojoBoundary{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts: List[bytes] = []

    for name, value in fields.items():
        parts.append(f"--{boundary}".encode("utf-8"))
        parts.append(f'Content-Disposition: form-data; name="{name}"'.encode("utf-8"))
        parts.append(b"")
        parts.append(str(value).encode("utf-8"))

    parts.append(f"--{boundary}".encode("utf-8"))
    parts.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"'.encode("utf-8")
    )
    parts.append(f"Content-Type: {content_type}".encode("utf-8"))
    parts.append(b"")
    parts.append(file_bytes)
    parts.append(f"--{boundary}--".encode("utf-8"))
    parts.append(b"")

    body = crlf.join(parts)
    header_ct = f"multipart/form-data; boundary={boundary}"
    return body, header_ct


class DefectDojoAPIClient:
    """Cliente HTTP real para la API REST v2 de OWASP DefectDojo (solo stdlib)."""

    def __init__(self, base_url: str, api_key: str, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Accept": "application/json",
            "User-Agent": "INSEGUS-DevSecOps-Pipeline/1.0",
        }
        if extra:
            headers.update(extra)
        return headers

    def _request_json(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"

        data = None
        extra_headers: Dict[str, str] = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            extra_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(
            url, data=data, headers=self._headers(extra_headers), method=method
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}

    def _request_multipart(
        self,
        endpoint: str,
        fields: Dict[str, str],
        filepath: str,
        file_field: str = "file",
        override_filename: Optional[str] = None,
        override_bytes: Optional[bytes] = None,
        content_type: str = "application/json",
    ) -> Any:
        if override_bytes is not None:
            file_bytes = override_bytes
        else:
            with open(filepath, "rb") as f:
                file_bytes = f.read()

        body, multipart_ct = _encode_multipart_formdata(
            fields=fields,
            file_field=file_field,
            filename=override_filename or os.path.basename(filepath),
            file_bytes=file_bytes,
            content_type=content_type,
        )
        req = urllib.request.Request(
            f"{self.base_url}{endpoint}",
            data=body,
            headers=self._headers({"Content-Type": multipart_ct}),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}

    def ensure_product_type(self, name: str = "Web Applications") -> int:
        res = self._request_json("GET", "/api/v2/product_types/", params={"name": name})
        results = res.get("results", [])
        if results:
            return int(results[0]["id"])
        created = self._request_json(
            "POST",
            "/api/v2/product_types/",
            payload={"name": name, "description": "Aplicaciones web INSEGUS DevSecOps"},
        )
        return int(created["id"])

    def ensure_product(self, product_name: str) -> int:
        res = self._request_json("GET", "/api/v2/products/", params={"name": product_name})
        for p in res.get("results", []):
            if p.get("name") == product_name:
                return int(p["id"])
        prod_type_id = self.ensure_product_type()
        created = self._request_json(
            "POST",
            "/api/v2/products/",
            payload={
                "name": product_name,
                "description": "Microservicio web INSEGUS - Pipeline DevSecOps (Security Team 3)",
                "prod_type": prod_type_id,
            },
        )
        return int(created["id"])

    def ensure_engagement(self, product_id: int, engagement_name: str) -> int:
        res = self._request_json(
            "GET",
            "/api/v2/engagements/",
            params={"product": product_id, "name": engagement_name},
        )
        for e in res.get("results", []):
            if e.get("name") == engagement_name:
                return int(e["id"])

        today = datetime.date.today()
        end_date = today + datetime.timedelta(days=30)
        created = self._request_json(
            "POST",
            "/api/v2/engagements/",
            payload={
                "name": engagement_name,
                "product": product_id,
                "target_start": today.isoformat(),
                "target_end": end_date.isoformat(),
                "engagement_type": "CI/CD",
                "status": "In Progress",
                "deduplication_on_engagement": True,
                "description": "Ejecución automatizada desde GitHub Actions (SAST, SCA, IaC, DAST)",
            },
        )
        return int(created["id"])

    def import_scan(
        self,
        engagement_id: int,
        scan_type: str,
        filepath: str,
        test_title: str,
    ) -> Dict[str, Any]:
        fields = {
            "engagement": str(engagement_id),
            "scan_type": scan_type,
            "test_title": test_title,
            "active": "true",
            "verified": "true",
            "deduplication_on_engagement": "true",
            "close_old_findings": "false",
            "scan_date": datetime.date.today().isoformat(),
        }
        # El parser nativo 'ZAP Scan' de DefectDojo requiere formato XML (.xml)
        if scan_type == "ZAP Scan" and filepath.lower().endswith(".json"):
            with open(filepath, "r", encoding="utf-8") as f:
                zap_xml = _zap_json_to_xml_bytes(json.load(f))
            return self._request_multipart(
                "/api/v2/import-scan/",
                fields=fields,
                filepath=filepath,
                override_filename="zap_report.xml",
                override_bytes=zap_xml,
                content_type="application/xml",
            )
        return self._request_multipart("/api/v2/import-scan/", fields=fields, filepath=filepath)

    def list_findings(self, engagement_id: int, limit: int = 500) -> List[Dict[str, Any]]:
        res = self._request_json(
            "GET",
            "/api/v2/findings/",
            params={"test__engagement": engagement_id, "limit": limit},
        )
        return res.get("results", [])

    def patch_finding(self, finding_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request_json("PATCH", f"/api/v2/findings/{finding_id}/", payload=payload)

    def add_finding_note(self, finding_id: int, note: str) -> Dict[str, Any]:
        return self._request_json(
            "POST", f"/api/v2/findings/{finding_id}/notes/", payload={"entry": note}
        )


def _summarize_findings(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
    active_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
    fp_count = 0
    mitigated_count = 0

    for f in findings:
        sev = str(f.get("severity", "Info")).capitalize()
        if sev not in counts:
            sev = "Info"
        counts[sev] += 1
        if f.get("false_p"):
            fp_count += 1
        elif f.get("is_mitigated"):
            mitigated_count += 1
        elif f.get("active", True):
            active_counts[sev] += 1

    return {
        "total_findings": len(findings),
        "by_severity_total": counts,
        "by_severity_active": active_counts,
        "false_positives": fp_count,
        "mitigated": mitigated_count,
    }


def _print_summary(summary: Dict[str, Any], header: str):
    print("\n" + "=" * 80)
    print(f"      {header}")
    print("=" * 80)
    print(f"Total Hallazgos Registrados:  {summary['total_findings']}")
    print(f"  - Críticas:                {summary['by_severity_total']['Critical']}")
    print(f"  - Altas:                   {summary['by_severity_total']['High']}")
    print(f"  - Medias:                  {summary['by_severity_total']['Medium']}")
    print(f"  - Bajas:                   {summary['by_severity_total']['Low']}")
    print(f"  - Informativas:            {summary['by_severity_total']['Info']}")
    print("=" * 80)


def _run_api_import(
    client: DefectDojoAPIClient,
    product_name: str,
    engagement_name: str,
    semgrep_path: str,
    trivy_sca_path: str,
    trivy_iac_path: str,
    zap_path: str,
):
    print(f"[*] Conectando con DefectDojo API REST v2 en: {client.base_url}")
    product_id = client.ensure_product(product_name)
    engagement_id = client.ensure_engagement(product_id, engagement_name)
    print(f"    Producto:   {product_name} (ID: {product_id})")
    print(f"    Engagement: {engagement_name} (ID: {engagement_id})")

    scans = [
        ("SAST", "Semgrep JSON Report", "SAST - Semgrep CE", semgrep_path),
        ("SCA", "Trivy Scan", "SCA - Trivy Dependencies", trivy_sca_path),
        ("IaC", "Trivy Scan", "IaC - Trivy Config (Docker/K8s)", trivy_iac_path),
        ("DAST", "ZAP Scan", "DAST - OWASP ZAP", zap_path),
    ]

    for label, scan_type, test_title, path in scans:
        if path and os.path.exists(path):
            print(f"\n[+] POST /api/v2/import-scan/ [{label} | {scan_type}]: {path}")
            resp = client.import_scan(
                engagement_id=engagement_id,
                scan_type=scan_type,
                filepath=path,
                test_title=test_title,
            )
            test_id = resp.get("test", "N/A")
            print(f"    -> [OK] Informe importado correctamente (Test ID: {test_id}). Deduplicación: ACTIVA.")
        else:
            print(f"[-] No se encontró reporte {label} en: {path}")

    findings = client.list_findings(engagement_id)
    summary = _summarize_findings(findings)
    _print_summary(summary, "RESUMEN CONSOLIDADO EN DEFECTDOJO API v2 (INSTANCIA REAL)")


def _run_api_triage(client: DefectDojoAPIClient, product_name: str, engagement_name: str):
    print(f"[*] Ejecutando triaje vía DefectDojo API REST v2 en: {client.base_url}")
    product_id = client.ensure_product(product_name)
    engagement_id = client.ensure_engagement(product_id, engagement_name)
    findings = client.list_findings(engagement_id)

    for f in findings:
        title_desc = f"{f.get('title', '')} {f.get('description', '')}".lower()
        if "cors" in title_desc and not f.get("false_p"):
            fid = int(f["id"])
            client.patch_finding(fid, {"false_p": True, "active": False, "verified": False})
            try:
                client.add_finding_note(fid, f"Falso Positivo justificado (ST3): {CORS_FP_REASON}")
            except Exception as note_err:
                print(f"    [!] Nota no añadida en #{fid}: {note_err}")
            print(f"[+] Hallazgo #{fid} ('{f.get('title')}') marcado como FALSO POSITIVO vía API v2.")
            break

    for f in findings:
        title_desc = f"{f.get('title', '')} {f.get('description', '')}".lower()
        if ("debug" in title_desc or "development" in title_desc) and not f.get("is_mitigated"):
            fid = int(f["id"])
            client.patch_finding(fid, {"is_mitigated": True, "active": False})
            try:
                client.add_finding_note(fid, f"Mitigado (ST3): {DEBUG_MITIGATED_NOTE}")
            except Exception as note_err:
                print(f"    [!] Nota no añadida en #{fid}: {note_err}")
            print(f"[+] Hallazgo #{fid} ('{f.get('title')}') marcado como MITIGADO vía API v2.")
            break

    updated_findings = client.list_findings(engagement_id)
    summary = _summarize_findings(updated_findings)
    print("\n[+] Resumen Post-Triaje (API v2):")
    print(f"    Total Activas:    {sum(summary['by_severity_active'].values())}")
    print(f"    Falsos Positivos: {summary['false_positives']}")
    print(f"    Mitigadas:        {summary['mitigated']}")


def _write_github_summary(
    summary: Dict[str, Any],
    product_name: str,
    engagement_name: str,
    source_label: str,
):
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "")
    if not summary_file:
        return
    tot = summary["by_severity_total"]
    act = summary["by_severity_active"]
    lines = [
        "## 📋 Gestión Centralizada de Vulnerabilidades — DefectDojo (API v2)",
        "",
        f"- **Producto:** `{product_name}` · **Engagement:** `{engagement_name}`",
        f"- **Origen de sincronización:** `{source_label}`",
        "",
        "| Métrica | Valor |",
        "| :--- | :---: |",
        f"| **Total hallazgos deduplicados** | **{summary['total_findings']}** |",
        f"| Activas tras triaje | {sum(act.values())} |",
        f"| Falsos Positivos justificados (`False Positive`) | {summary['false_positives']} |",
        f"| Mitigadas (`Mitigated`) | {summary['mitigated']} |",
        "",
        "| Severidad | Registradas | Activas |",
        "| :--- | :---: | :---: |",
        f"| 🔴 Críticas | {tot['Critical']} | {act['Critical']} |",
        f"| 🟠 Altas | {tot['High']} | {act['High']} |",
        f"| 🟡 Medias | {tot['Medium']} | {act['Medium']} |",
        f"| 🔵 Bajas | {tot['Low']} | {act['Low']} |",
        f"| ⚪ Informativas | {tot['Info']} | {act['Info']} |",
        "",
    ]
    with open(summary_file, "a", encoding="utf-8") as sf:
        sf.write("\n".join(lines) + "\n")


def _run_api_export(
    client: DefectDojoAPIClient,
    product_name: str,
    engagement_name: str,
    output_file: str,
):
    product_id = client.ensure_product(product_name)
    engagement_id = client.ensure_engagement(product_id, engagement_name)
    findings = client.list_findings(engagement_id)
    summary = _summarize_findings(findings)

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "defectdojo_api_v2",
                "defectdojo_url": client.base_url,
                "product": {"id": product_id, "name": product_name},
                "engagement": {"id": engagement_id, "name": engagement_name},
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "summary": summary,
                "findings_detail": findings,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"[+] Resumen consolidado exportado desde DefectDojo API v2 a: {output_file}")
    _write_github_summary(summary, product_name, engagement_name, f"API REST v2 ({client.base_url})")


def run_mock_import(semgrep_path: str, trivy_sca_path: str, trivy_iac_path: str, zap_path: str):
    db = DefectDojoDatabase()
    print("[*] Usando backend local compatible con DefectDojo API v2 (mock_defectdojo.py)...")
    print("    Producto:   INSEGUS Web Application (ID: 1)")
    print("    Engagement: DevSecOps CI/CD Pipeline (ID: 10)")

    if semgrep_path and os.path.exists(semgrep_path):
        print(f"\n[+] Enviando reporte SAST (/api/v2/import-scan/): {semgrep_path}")
        with open(semgrep_path, "r", encoding="utf-8") as f:
            count = db.import_semgrep(json.load(f), engagement_id=10)
            print(f"    -> [OK] Importados {count} hallazgos SAST (Semgrep JSON Report). Deduplicación: ACTIVA.")
    else:
        print(f"[-] No se encontró reporte Semgrep en: {semgrep_path}")

    if trivy_sca_path and os.path.exists(trivy_sca_path):
        print(f"\n[+] Enviando reporte SCA (/api/v2/import-scan/): {trivy_sca_path}")
        with open(trivy_sca_path, "r", encoding="utf-8") as f:
            count = db.import_trivy(json.load(f), scan_type="SCA", engagement_id=10)
            print(f"    -> [OK] Importados {count} hallazgos SCA (Trivy Dependencies). Deduplicación: ACTIVA.")
    else:
        print(f"[-] No se encontró reporte Trivy SCA en: {trivy_sca_path}")

    if trivy_iac_path and os.path.exists(trivy_iac_path):
        print(f"\n[+] Enviando reporte IaC (/api/v2/import-scan/): {trivy_iac_path}")
        with open(trivy_iac_path, "r", encoding="utf-8") as f:
            count = db.import_trivy(json.load(f), scan_type="IaC", engagement_id=10)
            print(f"    -> [OK] Importados {count} hallazgos IaC (Trivy Dockerfile/K8s). Deduplicación: ACTIVA.")
    else:
        print(f"[-] No se encontró reporte Trivy IaC en: {trivy_iac_path}")

    if zap_path and os.path.exists(zap_path):
        print(f"\n[+] Enviando reporte DAST (/api/v2/import-scan/): {zap_path}")
        with open(zap_path, "r", encoding="utf-8") as f:
            count = db.import_zap(json.load(f), engagement_id=10)
            print(f"    -> [OK] Importados {count} hallazgos DAST (OWASP ZAP). Deduplicación: ACTIVA.")
    else:
        print(f"[-] No se encontró reporte ZAP en: {zap_path}")

    _print_summary(db.get_summary(), "RESUMEN CONSOLIDADO DE VULNERABILIDADES EN DEFECTDOJO API v2")


def run_mock_triage():
    db = DefectDojoDatabase()
    print("[*] Iniciando proceso de triaje de vulnerabilidades en DefectDojo (backend local)...")

    for f in db.findings:
        if "cors" in f.get("title", "").lower() or "cors" in f.get("description", "").lower():
            db.mark_false_positive(finding_id=f["id"], reason=CORS_FP_REASON)
            print(f"[+] Hallazgo #{f['id']} ('{f['title']}') marcado como FALSO POSITIVO con justificación técnica.")
            break

    for f in db.findings:
        if "debug" in f.get("title", "").lower() or "development" in f.get("description", "").lower():
            db.mark_mitigated(finding_id=f["id"], notes=DEBUG_MITIGATED_NOTE)
            print(f"[+] Hallazgo #{f['id']} ('{f['title']}') marcado como MITIGADO.")
            break

    summary = db.get_summary()
    print("\n[+] Resumen Post-Triaje:")
    print(f"    Total Activas:    {sum(summary['by_severity_active'].values())}")
    print(f"    Falsos Positivos: {summary['false_positives']}")
    print(f"    Mitigadas:        {summary['mitigated']}")


def run_mock_export(output_file: str, product_name: str = "INSEGUS Web Application", engagement_name: str = "DevSecOps CI/CD Pipeline"):
    db = DefectDojoDatabase()
    summary = db.get_summary()
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": "mock_defectdojo_local",
                "summary": summary,
                "findings_detail": db.findings,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"[+] Resumen exportado a: {output_file}")
    _write_github_summary(summary, product_name, engagement_name, "Backend local compatible API v2 (mock_defectdojo.py)")


def main():
    parser = argparse.ArgumentParser(description="DefectDojo API v2 Client - PAI 4 DevSecOps")
    parser.add_argument("--action", choices=["import", "triage", "export"], required=True)
    parser.add_argument("--url", default=os.environ.get("DEFECTDOJO_URL", ""), help="URL base de DefectDojo")
    parser.add_argument("--api-key", default=os.environ.get("DEFECTDOJO_API_KEY", ""), help="API Key v2 de DefectDojo")
    parser.add_argument("--product", default=os.environ.get("PRODUCT_NAME", "INSEGUS Web Application"))
    parser.add_argument("--engagement", default=os.environ.get("ENGAGEMENT_NAME", "DevSecOps CI/CD Pipeline"))
    parser.add_argument("--semgrep", default="", help="Ruta reporte Semgrep JSON")
    parser.add_argument("--trivy-sca", default="", help="Ruta reporte Trivy SCA JSON")
    parser.add_argument("--trivy-iac", default="", help="Ruta reporte Trivy IaC JSON")
    parser.add_argument("--zap", default="", help="Ruta reporte ZAP JSON")
    parser.add_argument("--output", default="evidencias/defectdojo/defectdojo_consolidated.json")
    parser.add_argument(
        "--strict-api",
        action="store_true",
        help="Falla con exit 1 si la instancia remota de DefectDojo no responde (sin fallback al mock)",
    )

    args = parser.parse_args()
    use_real_api = bool(args.url.strip() and args.api_key.strip())

    if use_real_api:
        client = DefectDojoAPIClient(base_url=args.url, api_key=args.api_key)
        try:
            if args.action == "import":
                _run_api_import(
                    client,
                    args.product,
                    args.engagement,
                    args.semgrep,
                    args.trivy_sca,
                    args.trivy_iac,
                    args.zap,
                )
            elif args.action == "triage":
                _run_api_triage(client, args.product, args.engagement)
            elif args.action == "export":
                _run_api_export(client, args.product, args.engagement, args.output)
            return
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            print(f"[!] Error comunicando con DefectDojo API v2 ({args.url}): {exc}")
            if args.strict_api:
                sys.exit(1)
            print("[i] Conmutando automáticamente a backend local compatible (mock_defectdojo.py)...")
    else:
        print(
            "[i] DEFECTDOJO_URL / DEFECTDOJO_API_KEY no configuradas. "
            "Usando backend local compatible (mock_defectdojo.py)."
        )

    if args.action == "import":
        run_mock_import(args.semgrep, args.trivy_sca, args.trivy_iac, args.zap)
    elif args.action == "triage":
        run_mock_triage()
    elif args.action == "export":
        run_mock_export(args.output, args.product, args.engagement)


if __name__ == "__main__":
    main()
