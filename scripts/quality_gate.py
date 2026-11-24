#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
========================================================================================
EVALUADOR DE QUALITY GATES DE SEGURIDAD - PAI 4 (DEVSECOPS)
Módulo: quality_gate.py
Equipo: Security Team 3 (Grupo 3) - INSEGUS Yellow/Green Team
Asignatura: Seguridad en Sistemas Informáticos y en Internet
========================================================================================
Evalúa los informes de las herramientas de seguridad (Semgrep, Trivy SCA, Trivy IaC,
OWASP ZAP) en Gate A (Modo Aviso) y los hallazgos activos consolidados post-triaje de
OWASP DefectDojo (--defectdojo-report) en Gate B (Modo Bloqueante).
========================================================================================
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List, Optional


EMPTY_COUNTS = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "INFO": 0}


def _new_counts() -> Dict[str, int]:
    return dict(EMPTY_COUNTS)


def parse_semgrep_report(filepath: str) -> Dict[str, int]:
    counts = _new_counts()
    if not filepath or not os.path.exists(filepath):
        return counts
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            for result in data.get("results", []):
                sev = result.get("extra", {}).get("severity", "WARNING").upper()
                # Alineado con el parser 'Semgrep JSON Report' de DefectDojo
                if sev == "CRITICAL":
                    counts["CRITICAL"] += 1
                elif sev == "ERROR":
                    counts["HIGH"] += 1
                elif sev == "WARNING":
                    counts["MEDIUM"] += 1
                elif sev == "INFO":
                    counts["LOW"] += 1
    except Exception as e:
        print(f"[-] Error parseando Semgrep ({filepath}): {e}")
    return counts


def parse_trivy_report(filepath: str) -> Dict[str, int]:
    counts = _new_counts()
    if not filepath or not os.path.exists(filepath):
        return counts
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            results = data.get("Results", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            for res in results:
                for vuln in res.get("Vulnerabilities", []) or []:
                    sev = vuln.get("Severity", "UNKNOWN").upper()
                    if sev in counts:
                        counts[sev] += 1
                for misconf in res.get("Misconfigurations", []) or []:
                    sev = misconf.get("Severity", "UNKNOWN").upper()
                    if sev in counts:
                        counts[sev] += 1
    except Exception as e:
        print(f"[-] Error parseando Trivy ({filepath}): {e}")
    return counts


def parse_zap_report(filepath: str) -> Dict[str, int]:
    counts = _new_counts()
    if not filepath or not os.path.exists(filepath):
        return counts
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            for site in data.get("site", []):
                for alert in site.get("alerts", []):
                    riskcode = str(alert.get("riskcode", "1"))
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


def _norm_dd_sev(sev_dict: Dict[str, Any]) -> Dict[str, int]:
    counts = _new_counts()
    for key, target in (
        ("Critical", "CRITICAL"),
        ("CRITICAL", "CRITICAL"),
        ("High", "HIGH"),
        ("HIGH", "HIGH"),
        ("Medium", "MEDIUM"),
        ("MEDIUM", "MEDIUM"),
        ("Low", "LOW"),
        ("LOW", "LOW"),
        ("Info", "INFO"),
        ("INFO", "INFO"),
    ):
        if key in sev_dict:
            counts[target] = int(sev_dict.get(key, 0) or 0)
    return counts


def parse_defectdojo_consolidated(filepath: str) -> Dict[str, Any]:
    """Lee el resumen consolidado de DefectDojo (activos deduplicados post-triaje)."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    summary = data.get("summary", {})
    by_tool = summary.get("by_tool_active", {})
    return {
        "source": data.get("source", "defectdojo"),
        "defectdojo_url": data.get("defectdojo_url", ""),
        "total_unique": int(summary.get("total_findings", 0)),
        "duplicates": int(summary.get("duplicates", 0)),
        "false_positives": int(summary.get("false_positives", 0)),
        "mitigated": int(summary.get("mitigated", 0)),
        "totals": _norm_dd_sev(summary.get("by_severity_active", {})),
        "sast": _norm_dd_sev(by_tool.get("SAST", {})),
        "sca": _norm_dd_sev(by_tool.get("SCA", {})),
        "iac": _norm_dd_sev(by_tool.get("IaC", {})),
        "dast": _norm_dd_sev(by_tool.get("DAST", {})),
    }


def write_markdown_summary(
    summary_file: str,
    mode: str,
    sast: Dict[str, int],
    sca: Dict[str, int],
    iac: Dict[str, int],
    dast: Dict[str, int],
    totals: Dict[str, int],
    threshold_critical: int,
    threshold_high: int,
    threshold_medium: int,
    breaches: List[str],
    passed: bool,
    dd_meta: Optional[Dict[str, Any]] = None,
):
    if not summary_file:
        return

    is_advisory = mode.lower() == "advisory"
    gate_label = (
        "Quality Gate A — Modo Aviso (Análisis Estático)"
        if is_advisory
        else "Quality Gate B — Modo Bloqueante (Pre-Producción)"
    )
    if is_advisory:
        status_badge = (
            "🟡 **ADVERTENCIA (Modo Aviso — `continue-on-error: true`, Exit Code `0`)**"
            if breaches
            else "🟢 **APROBADO (Exit Code `0`)**"
        )
    else:
        status_badge = (
            "🟢 **APROBADO — Paso a Producción autorizado (Exit Code `0`)**"
            if passed
            else "🔴 **BLOQUEADO — Despliegue a Producción detenido (Exit Code `1`)**"
        )

    lines = [
        f"## 🛡️ {gate_label}",
        "",
        f"**Estado:** {status_badge}",
    ]
    if dd_meta:
        lines.append(
            f"**Fuente evaluada:** DefectDojo (`{dd_meta['source']}`) · Únicos: `{dd_meta['total_unique']}` · Duplicados excluidos: `{dd_meta['duplicates']}` · Falsos Positivos triados: `{dd_meta['false_positives']}`"
        )
    lines.extend([
        "",
        "| Herramienta / Capa | Críticas | Altas | Medias | Bajas |",
        "| :--- | :---: | :---: | :---: | :---: |",
        f"| **SAST** (Semgrep CE) | {sast['CRITICAL']} | {sast['HIGH']} | {sast['MEDIUM']} | {sast['LOW']} |",
        f"| **SCA** (Trivy Dependencies) | {sca['CRITICAL']} | {sca['HIGH']} | {sca['MEDIUM']} | {sca['LOW']} |",
        f"| **IaC** (Trivy Docker/K8s) | {iac['CRITICAL']} | {iac['HIGH']} | {iac['MEDIUM']} | {iac['LOW']} |",
    ])
    if not is_advisory:
        lines.append(
            f"| **DAST** (OWASP ZAP) | {dast['CRITICAL']} | {dast['HIGH']} | {dast['MEDIUM']} | {dast['LOW']} |"
        )
    lines.extend([
        f"| **TOTAL {'ACTIVOS POST-TRIAJE' if dd_meta else 'CONSOLIDADO'}** | **{totals['CRITICAL']}** | **{totals['HIGH']}** | **{totals['MEDIUM']}** | **{totals['LOW']}** |",
        "",
        "| Severidad | Detectadas | Umbral Permitido | Resultado |",
        "| :--- | :---: | :---: | :---: |",
        f"| **Críticas** | {totals['CRITICAL']} | `≤ {threshold_critical}` | {'❌ Superado' if totals['CRITICAL'] > threshold_critical else '✅ OK'} |",
        f"| **Altas** | {totals['HIGH']} | `≤ {threshold_high}` | {'❌ Superado' if totals['HIGH'] > threshold_high else '✅ OK'} |",
        f"| **Medias** | {totals['MEDIUM']} | `≤ {threshold_medium}` | {'❌ Superado' if totals['MEDIUM'] > threshold_medium else '✅ OK'} |",
        "",
    ])
    if is_advisory and breaches:
        lines.append(
            "> ℹ️ **Motivo de continuación:** Este gate opera en modo aviso para permitir el despliegue en *staging* y la ejecución de las pruebas dinámicas (DAST / OWASP ZAP)."
        )
        lines.append("")
    elif not is_advisory and not passed:
        lines.append(
            "> ⛔ **Acción del pipeline:** Se han superado los umbrales de seguridad de release sobre hallazgos activos en DefectDojo. El pipeline finaliza con `exit 1` y bloquea el despliegue en Kubernetes."
        )
        lines.append("")

    with open(summary_file, "a", encoding="utf-8") as sf:
        sf.write("\n".join(lines) + "\n")


def evaluate_quality_gate(
    semgrep_file: str,
    trivy_sca_file: str,
    trivy_iac_file: str,
    zap_file: str,
    mode: str,
    threshold_critical: int = 0,
    threshold_high: int = 0,
    threshold_medium: int = 10,
    summary_file: str = "",
    defectdojo_file: str = "",
) -> bool:
    print("=" * 80)
    print("      INSEGUS DEVSECOPS - MOTOR DE EVALUACIÓN DE QUALITY GATES (ST3)       ")
    print("=" * 80)

    dd_meta: Optional[Dict[str, Any]] = None
    if defectdojo_file and os.path.exists(defectdojo_file):
        dd_meta = parse_defectdojo_consolidated(defectdojo_file)
        sast = dd_meta["sast"]
        sca = dd_meta["sca"]
        iac = dd_meta["iac"]
        dast = dd_meta["dast"]
        totals = dd_meta["totals"]
        print(f"\n[+] MODO DE EJECUCIÓN DEL GATE: {mode.upper()} (FUENTE: DEFECTDOJO API v2 POST-TRIAJE)")
        print(
            f"[+] Inventario DefectDojo: {dd_meta['total_unique']} únicos | "
            f"{dd_meta['duplicates']} duplicados excluidos | "
            f"{dd_meta['false_positives']} falso(s) positivo(s) triado(s)"
        )
    else:
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
    total_label = "TOTAL ACTIVOS DEFECTDOJO" if dd_meta else "TOTAL CONSOLIDADO"
    print(f"{total_label:<25} | {totals['CRITICAL']:<8} | {totals['HIGH']:<6} | {totals['MEDIUM']:<8} | {totals['LOW']:<6}")
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
        write_markdown_summary(
            summary_file, mode, sast, sca, iac, dast, totals,
            threshold_critical, threshold_high, threshold_medium, breaches, True, dd_meta
        )
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
            write_markdown_summary(
                summary_file, mode, sast, sca, iac, dast, totals,
                threshold_critical, threshold_high, threshold_medium, breaches, False, dd_meta
            )
            return False
        else:
            print("    [+] Postura de seguridad verificada. Cero vulnerabilidades críticas o altas y medias en umbral.")
            print("    [+] Autorización concedida para despliegue en Producción.")
            print("\n[RESULTADO] Quality Gate B (Modo Bloqueante) -> APROBADO (Exit Code 0)\n")
            write_markdown_summary(
                summary_file, mode, sast, sca, iac, dast, totals,
                threshold_critical, threshold_high, threshold_medium, breaches, True, dd_meta
            )
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
    parser.add_argument("--defectdojo-report", default="", help="Ruta al resumen consolidado de DefectDojo (defectdojo_consolidated.json)")
    parser.add_argument("--critical", type=int, default=0, help="Umbral máximo de vulnerabilidades críticas")
    parser.add_argument("--high", type=int, default=0, help="Umbral máximo de vulnerabilidades altas")
    parser.add_argument("--medium", type=int, default=10, help="Umbral máximo de vulnerabilidades medias")
    parser.add_argument(
        "--summary-file",
        default=os.environ.get("GITHUB_STEP_SUMMARY", ""),
        help="Ruta opcional para exportar resumen Markdown (compatible con GITHUB_STEP_SUMMARY)",
    )

    args = parser.parse_args()
    success = evaluate_quality_gate(
        semgrep_file=args.semgrep,
        trivy_sca_file=args.trivy_sca,
        trivy_iac_file=args.trivy_iac,
        zap_file=args.zap,
        mode=args.mode,
        threshold_critical=args.critical,
        threshold_high=args.high,
        threshold_medium=args.medium,
        summary_file=args.summary_file,
        defectdojo_file=args.defectdojo_report,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
