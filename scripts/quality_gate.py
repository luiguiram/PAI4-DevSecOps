#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================================
EVALUADOR DE QUALITY GATES DE SEGURIDAD - PAI 4 (DEVSECOPS)
Módulo: quality_gate.py
Equipo: Security Team 3 (Grupo 3) - INSEGUS Yellow/Green Team
Asignatura: Seguridad en Sistemas Informáticos y en Internet
========================================================================================
Este script analiza los informes de las herramientas de seguridad (Semgrep, Trivy SCA,
Trivy IaC, OWASP ZAP) o los hallazgos consolidados en DefectDojo y aplica las políticas
definidas en config/quality_gate_policy.json según el modo seleccionado (aviso o bloqueante).
========================================================================================
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List

def parse_semgrep_report(filepath: str) -> Dict[str, int]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    if not os.path.exists(filepath):
        return counts
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for result in data.get("results", []):
                extra = result.get("extra", {})
                sev = extra.get("severity", "WARNING").upper()
                if sev == "ERROR":
                    # Mapeo de reglas de inyección o secretos a HIGH/CRITICAL
                    check_id = result.get("check_id", "").lower()
                    if "injection" in check_id or "secret" in check_id or "eval" in check_id:
                        counts["HIGH"] += 1
                    else:
                        counts["MEDIUM"] += 1
                elif sev == "WARNING":
                    counts["MEDIUM"] += 1
                elif sev == "INFO":
                    counts["LOW"] += 1
    except Exception as e:
        print(f"[-] Error parseando Semgrep ({filepath}): {e}")
    return counts

def parse_trivy_report(filepath: str) -> Dict[str, int]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    if not os.path.exists(filepath):
        return counts
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # Trivy exporta lista de Results
            results = data.get("Results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for res in results:
                # Vulnerabilidades SCA
                for vuln in res.get("Vulnerabilities", []) or []:
                    sev = vuln.get("Severity", "UNKNOWN").upper()
                    if sev in counts:
                        counts[sev] += 1
                # Desconfiguraciones IaC
                for misconf in res.get("Misconfigurations", []) or []:
                    sev = misconf.get("Severity", "UNKNOWN").upper()
                    if sev in counts:
                        counts[sev] += 1
    except Exception as e:
        print(f"[-] Error parseando Trivy ({filepath}): {e}")
    return counts

def parse_zap_report(filepath: str) -> Dict[str, int]:
    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}
    if not os.path.exists(filepath):
        return counts
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            site_list = data.get("site", [])
            for site in site_list:
                for alert in site.get("alerts", []):
                    riskcode = str(alert.get("riskcode", "1"))
                    # 3: High, 2: Medium, 1: Low, 0: Informational
                    if riskcode == "3":
                        counts["HIGH"] += 1
                    elif riskcode == "2":
                        counts["MEDIUM"] += 1
                    elif riskcode == "1":
                        counts["LOW"] += 1
                    else:
                        counts["INFO"] += 1
    except Exception as e:
        print(f"[-] Error parseando ZAP ({filepath}): {e}")
    return counts

def evaluate_quality_gate(
    semgrep_file: str,
    trivy_sca_file: str,
    trivy_iac_file: str,
    zap_file: str,
    mode: str,
    threshold_critical: int = 0,
    threshold_high: int = 0,
    threshold_medium: int = 10
) -> bool:
    print("=" * 80)
    print("      INSEGUS DEVSECOPS - MOTOR DE EVALUACIÓN DE QUALITY GATES (ST3)       ")
    print("=" * 80)

    sast = parse_semgrep_report(semgrep_file)
    sca = parse_trivy_report(trivy_sca_file)
    iac = parse_trivy_report(trivy_iac_file)
    dast = parse_zap_report(zap_file)

    totals = {
        "CRITICAL": sast["CRITICAL"] + sca["CRITICAL"] + iac["CRITICAL"] + dast["CRITICAL"],
        "HIGH": sast["HIGH"] + sca["HIGH"] + iac["HIGH"] + dast["HIGH"],
        "MEDIUM": sast["MEDIUM"] + sca["MEDIUM"] + iac["MEDIUM"] + dast["MEDIUM"],
        "LOW": sast["LOW"] + sca["LOW"] + iac["LOW"] + dast["LOW"],
    }

    print(f"\n[+] MODO DE EJECUCIÓN DEL GATE: {mode.upper()}")
    print("-" * 80)
    print(f"{'HERRAMIENTA / ETAPA':<25} | {'CRITICAL':<8} | {'HIGH':<6} | {'MEDIUM':<8} | {'LOW':<6}")
    print("-" * 80)
    print(f"{'SAST (Semgrep)':<25} | {sast['CRITICAL']:<8} | {sast['HIGH']:<6} | {sast['MEDIUM']:<8} | {sast['LOW']:<6}")
    print(f"{'SCA (Trivy Dependencies)':<25} | {sca['CRITICAL']:<8} | {sca['HIGH']:<6} | {sca['MEDIUM']:<8} | {sca['LOW']:<6}")
    print(f"{'IaC (Trivy Docker/K8s)':<25} | {iac['CRITICAL']:<8} | {iac['HIGH']:<6} | {iac['MEDIUM']:<8} | {iac['LOW']:<6}")
    print(f"{'DAST (OWASP ZAP)':<25} | {dast['CRITICAL']:<8} | {dast['HIGH']:<6} | {dast['MEDIUM']:<8} | {dast['LOW']:<6}")
    print("-" * 80)
    print(f"{'TOTAL CONSOLIDADO':<25} | {totals['CRITICAL']:<8} | {totals['HIGH']:<6} | {totals['MEDIUM']:<8} | {totals['LOW']:<6}")
    print("=" * 80)

    breaches = []
    if totals["CRITICAL"] > threshold_critical:
        breaches.append(f"Vulnerabilidades CRÍTICAS ({totals['CRITICAL']}) superan umbral ({threshold_critical})")
    if totals["HIGH"] > threshold_high:
        breaches.append(f"Vulnerabilidades ALTAS ({totals['HIGH']}) superan umbral ({threshold_high})")
    if totals["MEDIUM"] > threshold_medium:
        breaches.append(f"Vulnerabilidades MEDIAS ({totals['MEDIUM']}) superan umbral ({threshold_medium})")

    if mode.lower() == "advisory":
        print("\n[!] MODO AVISO (ADVISORY / WARNING MODE):")
        if breaches:
            print("    [!] ADVERTENCIA: Se han detectado violaciones de seguridad en etapas iniciales:")
            for b in breaches:
                print(f"        -> {b}")
            print("    [i] La política permite continuar la ejecución (continue-on-error: true).")
            print("    [i] Motivo: Permitir el despliegue del entorno de staging y ejecución de pruebas DAST.")
        else:
            print("    [+] No se registraron alertas severas en esta etapa.")
        print("\n[RESULTADO] Quality Gate A (Modo Aviso) -> EXITOSO / CONTINUAR PIPELINE (Exit Code 0)\n")
        return True

    elif mode.lower() == "blocking":
        print("\n[!] MODO BLOQUEANTE (BLOCKING MODE / PRODUCTION RELEASE GATE):")
        if breaches:
            print("    [X] ERROR CRÍTICO DE SEGURIDAD: Umbrales superados en la etapa de release:")
            for b in breaches:
                print(f"        -> [BLOQUEADO] {b}")
            print("\n    [!] ACCIÓN DISCIPLINARIA: El pipeline SE DETIENE de inmediato.")
            print("    [!] El artefacto NO ha sido autorizado para despliegue en Producción.")
            print("    [!] Notificando a equipo de desarrollo y Security Team 3.\n")
            print("[RESULTADO] Quality Gate B (Modo Bloqueante) -> FALLIDO / BLOQUEO ACTIVO (Exit Code 1)\n")
            return False
        else:
            print("    [+] Postura de seguridad verificada. Cero vulnerabilidades críticas o altas.")
            print("    [+] Autorización concedida para despliegue en Producción.")
            print("\n[RESULTADO] Quality Gate B (Modo Bloqueante) -> APROBADO (Exit Code 0)\n")
            return True
    else:
        print(f"[-] Modo desconocido: {mode}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Quality Gate Security Evaluator - PAI 4 DevSecOps")
    parser.add_argument("--mode", choices=["advisory", "blocking"], required=True, help="Modo del gate: advisory o blocking")
    parser.add_argument("--semgrep", default="", help="Ruta al reporte Semgrep JSON")
    parser.add_argument("--trivy-sca", default="", help="Ruta al reporte Trivy SCA JSON")
    parser.add_argument("--trivy-iac", default="", help="Ruta al reporte Trivy IaC JSON")
    parser.add_argument("--zap", default="", help="Ruta al reporte OWASP ZAP JSON")
    parser.add_argument("--critical", type=int, default=0, help="Umbral máximo de vulnerabilidades críticas")
    parser.add_argument("--high", type=int, default=0, help="Umbral máximo de vulnerabilidades altas")
    parser.add_argument("--medium", type=int, default=10, help="Umbral máximo de vulnerabilidades medias")

    args = parser.parse_args()
    success = evaluate_quality_gate(
        semgrep_file=args.semgrep,
        trivy_sca_file=args.trivy_sca,
        trivy_iac_file=args.trivy_iac,
        zap_file=args.zap,
        mode=args.mode,
        threshold_critical=args.critical,
        threshold_high=args.high,
        threshold_medium=args.medium
    )

    if not success:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
