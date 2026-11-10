#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================================
SERVIDOR MOCK DE DEFECTDOJO API V2 - PAI 4 DEVSECOPS
Módulo: mock_defectdojo.py
Equipo: Security Team 3 (Grupo 3) - INSEGUS Yellow/Green Team
Asignatura: Seguridad en Sistemas Informáticos y en Internet
========================================================================================
Implementa una réplica funcional de la API v2 de DefectDojo (REST) para recepción,
almacenamiento, deduplicación, clasificación y triaje de informes de seguridad en CI/CD.
Soporta importación multipart de Semgrep JSON, Trivy Scan y OWASP ZAP.
========================================================================================
"""

import os
import sys
import json
import time
import hashlib
from typing import Dict, Any, List
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "evidencias", "defectdojo", "defectdojo_findings_db.json")

class DefectDojoDatabase:
    def __init__(self, filepath: str = DATA_FILE):
        self.filepath = filepath
        self.products = [
            {"id": 1, "name": "INSEGUS Web Application", "description": "Microservicio web para Kubernetes"}
        ]
        self.engagements = [
            {"id": 10, "product": 1, "name": "DevSecOps CI/CD Pipeline", "target_start": "2026-11-10", "status": "In Progress"}
        ]
        self.findings: List[Dict[str, Any]] = []
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.products = data.get("products", self.products)
                    self.engagements = data.get("engagements", self.engagements)
                    self.findings = data.get("findings", [])
            except Exception as e:
                print(f"[!] Error cargando DB DefectDojo: {e}")

    def save(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "products": self.products,
                "engagements": self.engagements,
                "findings": self.findings,
                "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }, f, indent=2, ensure_ascii=False)

    def import_semgrep(self, semgrep_data: Dict[str, Any], engagement_id: int = 10) -> int:
        count = 0
        for res in semgrep_data.get("results", []):
            rule_id = res.get("check_id", "semgrep-rule")
            extra = res.get("extra", {})
            msg = extra.get("message", "Semgrep finding")
            metadata = extra.get("metadata", {})
            cwe_str = metadata.get("cwe", "CWE-0")
            cwe_id = 0
            if "CWE-" in cwe_str:
                try:
                    cwe_id = int(cwe_str.split("CWE-")[1].split(":")[0].strip())
                except:
                    cwe_id = 0
            
            raw_sev = extra.get("severity", "WARNING").upper()
            if raw_sev == "ERROR":
                severity = "High" if ("injection" in rule_id.lower() or "secret" in rule_id.lower() or "eval" in rule_id.lower()) else "Medium"
            elif raw_sev == "WARNING":
                severity = "Medium"
            else:
                severity = "Low"

            file_path = res.get("path", "")
            start_line = res.get("start", {}).get("line", 0)
            vuln_hash = hashlib.sha256(f"{rule_id}:{file_path}:{start_line}".encode()).hexdigest()

            # Deduplicación por hash
            duplicate = False
            for f in self.findings:
                if f.get("unique_id_from_tool") == vuln_hash:
                    duplicate = True
                    f["duplicate"] = True
                    break

            if not duplicate:
                finding = {
                    "id": len(self.findings) + 1,
                    "title": f"Semgrep: {rule_id}",
                    "severity": severity,
                    "cwe": cwe_id,
                    "cwe_description": cwe_str,
                    "description": msg,
                    "file_path": file_path,
                    "line": start_line,
                    "active": True,
                    "verified": True,
                    "false_p": False,
                    "duplicate": False,
                    "scanner": "Semgrep CE",
                    "scan_type": "SAST",
                    "engagement": engagement_id,
                    "unique_id_from_tool": vuln_hash,
                    "date": time.strftime("%Y-%m-%d"),
                    "mitigation": "Sanitizar entradas con consultas parametrizadas o mover secretos a variables de entorno / Vault."
                }
                self.findings.append(finding)
                count += 1
        self.save()
        return count

    def import_trivy(self, trivy_data: Any, scan_type: str = "SCA", engagement_id: int = 10) -> int:
        count = 0
        results = trivy_data.get("Results", []) if isinstance(trivy_data, dict) else (trivy_data if isinstance(trivy_data, list) else [])
        for res in results:
            target = res.get("Target", "app")
            # Vulnerabilidades de paquetes
            for v in res.get("Vulnerabilities", []) or []:
                vuln_id = v.get("VulnerabilityID", "CVE-UNKNOWN")
                pkg_name = v.get("PkgName", "")
                installed_v = v.get("InstalledVersion", "")
                fixed_v = v.get("FixedVersion", "N/A")
                sev = v.get("Severity", "Medium").capitalize()
                title = v.get("Title") or f"{vuln_id} in {pkg_name}"
                cwe_ids = v.get("CweIDs", [0])
                cwe = cwe_ids[0] if cwe_ids else 0

                vuln_hash = hashlib.sha256(f"{vuln_id}:{pkg_name}:{target}".encode()).hexdigest()
                dup = any(f.get("unique_id_from_tool") == vuln_hash for f in self.findings)
                if not dup:
                    finding = {
                        "id": len(self.findings) + 1,
                        "title": f"Trivy SCA: {vuln_id} ({pkg_name}@{installed_v})",
                        "severity": sev,
                        "cwe": cwe if isinstance(cwe, int) else 0,
                        "cwe_description": str(cwe),
                        "description": v.get("Description", f"Vulnerabilidad conocida en {pkg_name}"),
                        "file_path": target,
                        "line": 0,
                        "active": True,
                        "verified": True,
                        "false_p": False,
                        "duplicate": False,
                        "scanner": "Trivy",
                        "scan_type": scan_type,
                        "engagement": engagement_id,
                        "unique_id_from_tool": vuln_hash,
                        "date": time.strftime("%Y-%m-%d"),
                        "mitigation": f"Actualizar el paquete {pkg_name} a la versión {fixed_v} o superior."
                    }
                    self.findings.append(finding)
                    count += 1

            # Desconfiguraciones de infraestructura
            for m in res.get("Misconfigurations", []) or []:
                m_id = m.get("ID", "MISCONF-UNKNOWN")
                sev = m.get("Severity", "Medium").capitalize()
                title = m.get("Title", "IaC Misconfiguration")
                vuln_hash = hashlib.sha256(f"{m_id}:{target}".encode()).hexdigest()
                dup = any(f.get("unique_id_from_tool") == vuln_hash for f in self.findings)
                if not dup:
                    finding = {
                        "id": len(self.findings) + 1,
                        "title": f"Trivy IaC: {m_id} - {title}",
                        "severity": sev,
                        "cwe": 16, # Configuration
                        "cwe_description": "CWE-16: Configuration",
                        "description": m.get("Description", title) + "\nResolución: " + m.get("Resolution", ""),
                        "file_path": target,
                        "line": 0,
                        "active": True,
                        "verified": True,
                        "false_p": False,
                        "duplicate": False,
                        "scanner": "Trivy IaC",
                        "scan_type": "IaC",
                        "engagement": engagement_id,
                        "unique_id_from_tool": vuln_hash,
                        "date": time.strftime("%Y-%m-%d"),
                        "mitigation": m.get("Resolution", "Ajustar manifiesto o Dockerfile según CIS Benchmark.")
                    }
                    self.findings.append(finding)
                    count += 1
        self.save()
        return count

    def import_zap(self, zap_data: Dict[str, Any], engagement_id: int = 10) -> int:
        count = 0
        site_list = zap_data.get("site", [])
        for site in site_list:
            host = site.get("@host", "localhost")
            for alert in site.get("alerts", []):
                alert_id = alert.get("pluginid", "0")
                alert_name = alert.get("alert", "ZAP Alert")
                risk = alert.get("riskdesc", "Medium").split(" ")[0].capitalize()
                cwe_id = int(alert.get("cweid", 0)) if str(alert.get("cweid", "0")).isdigit() else 0
                desc = alert.get("desc", alert_name)
                sol = alert.get("solution", "Aplicar hardening en servidor web.")
                vuln_hash = hashlib.sha256(f"{alert_id}:{alert_name}:{host}".encode()).hexdigest()

                dup = any(f.get("unique_id_from_tool") == vuln_hash for f in self.findings)
                if not dup:
                    finding = {
                        "id": len(self.findings) + 1,
                        "title": f"OWASP ZAP: {alert_name}",
                        "severity": risk,
                        "cwe": cwe_id,
                        "cwe_description": f"CWE-{cwe_id}",
                        "description": desc,
                        "file_path": alert.get("instances", [{}])[0].get("uri", host) if alert.get("instances") else host,
                        "line": 0,
                        "active": True,
                        "verified": True,
                        "false_p": False,
                        "duplicate": False,
                        "scanner": "OWASP ZAP",
                        "scan_type": "DAST",
                        "engagement": engagement_id,
                        "unique_id_from_tool": vuln_hash,
                        "date": time.strftime("%Y-%m-%d"),
                        "mitigation": sol
                    }
                    self.findings.append(finding)
                    count += 1
        self.save()
        return count

    def mark_false_positive(self, finding_id: int, reason: str) -> bool:
        for f in self.findings:
            if f.get("id") == finding_id:
                f["false_p"] = True
                f["active"] = False
                f["triage_notes"] = f"Marcado como Falso Positivo: {reason}"
                f["triaged_by"] = "Security Team 3"
                self.save()
                return True
        return False

    def mark_mitigated(self, finding_id: int, notes: str) -> bool:
        for f in self.findings:
            if f.get("id") == finding_id:
                f["is_mitigated"] = True
                f["active"] = False
                f["mitigation_notes"] = notes
                self.save()
                return True
        return False

    def get_summary(self) -> Dict[str, Any]:
        counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
        active_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Info": 0}
        fp_count = 0
        mitigated_count = 0

        for f in self.findings:
            sev = f.get("severity", "Info").capitalize()
            if sev in counts:
                counts[sev] += 1
            if f.get("false_p"):
                fp_count += 1
            elif f.get("is_mitigated"):
                mitigated_count += 1
            elif f.get("active"):
                if sev in active_counts:
                    active_counts[sev] += 1

        return {
            "total_findings": len(self.findings),
            "by_severity_total": counts,
            "by_severity_active": active_counts,
            "false_positives": fp_count,
            "mitigated": mitigated_count
        }

if __name__ == "__main__":
    db = DefectDojoDatabase()
    print(f"[+] Base de datos DefectDojo inicializada con {len(db.findings)} hallazgos.")
    summary = db.get_summary()
    print(json.dumps(summary, indent=2))
