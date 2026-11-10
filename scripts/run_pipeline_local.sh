#!/usr/bin/env bash
# ==============================================================================
# ORQUESTADOR LOCAL DEL PIPELINE DEVSECOPS - INSEGUS ENTERPRISE
# Módulo: run_pipeline_local.sh
# Equipo: Security Team 3 (Grupo 3) - PAI 4 DevSecOps
# Asignatura: Seguridad en Sistemas Informáticos y en Internet
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR="$BASE_DIR/app"
EVIDENCIAS_DIR="$BASE_DIR/evidencias"
LOGS_DIR="$EVIDENCIAS_DIR/pipeline_logs"

mkdir -p "$EVIDENCIAS_DIR"/{sast,sca,iac,dast,quality_gates,defectdojo,pipeline_logs,diagramas}

echo "================================================================================"
echo "    INSEGUS ENTERPRISE - EJECUCIÓN DEL PIPELINE DEVSECOPS (SECURITY TEAM 3)    "
echo "================================================================================"
echo "[*] Fecha y hora de ejecución: $(date)"
echo "[*] Directorio base: $BASE_DIR"

# ------------------------------------------------------------------------------
# ETAPA 1: BUILD Y PRUEBAS UNITARIAS
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 1] Compilación y ejecución de pruebas unitarias..."
(
  cd "$APP_DIR"
  npm test
)
echo "[+] Etapa 1 completada con éxito."

# ------------------------------------------------------------------------------
# ETAPA 2: ANÁLISIS ESTÁTICO DE CÓDIGO (SAST - SEMGREP)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 2] Análisis estático de código fuente con Semgrep CE..."
docker run --rm \
  -v "$BASE_DIR":/workspace \
  -w /workspace \
  semgrep/semgrep semgrep scan \
  --config /workspace/config/.semgrep.yml \
  --json -o /workspace/evidencias/sast/semgrep_report.json \
  /workspace/app || true

docker run --rm \
  -v "$BASE_DIR":/workspace \
  -w /workspace \
  semgrep/semgrep semgrep scan \
  --config /workspace/config/.semgrep.yml \
  --sarif -o /workspace/evidencias/sast/semgrep_report.sarif \
  /workspace/app || true
echo "[+] Reportes Semgrep generados en evidencias/sast/."

# ------------------------------------------------------------------------------
# ETAPA 3: ANÁLISIS DE DEPENDENCIAS Y COMPOSICIÓN DE SOFTWARE (SCA - TRIVY)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 3] Análisis de dependencias de terceros (SCA) con Trivy..."
docker run --rm \
  -v "$BASE_DIR":/workspace \
  aquasec/trivy:latest fs \
  --db-repository ghcr.io/aquasecurity/trivy-db:2 \
  --format json \
  -o /workspace/evidencias/sca/trivy_sca_report.json \
  /workspace/app
echo "[+] Reporte Trivy SCA generado en evidencias/sca/trivy_sca_report.json."

# ------------------------------------------------------------------------------
# ETAPA 4: ANÁLISIS DE SEGURIDAD EN INFRAESTRUCTURA COMO CÓDIGO (IaC - TRIVY)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 4] Auditoría de Dockerfile y Manifiestos Kubernetes (IaC) con Trivy..."
docker run --rm \
  -v "$BASE_DIR":/workspace \
  aquasec/trivy:latest config \
  --format json \
  -o /workspace/evidencias/iac/trivy_iac_report.json \
  /workspace/app
echo "[+] Reporte Trivy IaC generado en evidencias/iac/trivy_iac_report.json."

# ------------------------------------------------------------------------------
# QUALITY GATE A: MODO AVISO (ADVISORY QUALITY GATE)
# ------------------------------------------------------------------------------
echo -e "\n[QUALITY GATE A] Evaluación de Quality Gate A en Modo Aviso..."
python3 "$SCRIPT_DIR/quality_gate.py" \
  --mode advisory \
  --semgrep "$EVIDENCIAS_DIR/sast/semgrep_report.json" \
  --trivy-sca "$EVIDENCIAS_DIR/sca/trivy_sca_report.json" \
  --trivy-iac "$EVIDENCIAS_DIR/iac/trivy_iac_report.json" \
  | tee "$EVIDENCIAS_DIR/quality_gates/quality_gate_warning_mode.log"
echo "[+] Quality Gate A evaluado (no bloqueante, continue-on-error: true)."

# ------------------------------------------------------------------------------
# ETAPA 5: DESPLIEGUE EN STAGING Y PRUEBAS DINÁMICAS (DAST - OWASP ZAP)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 5] Despliegue en Staging y Análisis Dinámico (DAST)..."
python3 "$SCRIPT_DIR/run_zap_dast.py"
echo "[+] Reportes DAST generados en evidencias/dast/ (JSON y HTML)."

# ------------------------------------------------------------------------------
# ETAPA 6: CENTRALIZACIÓN Y TRIAJE EN DEFECTDOJO API v2
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 6] Ingesta y consolidación en DefectDojo API v2..."
python3 "$SCRIPT_DIR/defectdojo_client.py" \
  --action import \
  --semgrep "$EVIDENCIAS_DIR/sast/semgrep_report.json" \
  --trivy-sca "$EVIDENCIAS_DIR/sca/trivy_sca_report.json" \
  --trivy-iac "$EVIDENCIAS_DIR/iac/trivy_iac_report.json" \
  --zap "$EVIDENCIAS_DIR/dast/zap_report.json"

python3 "$SCRIPT_DIR/defectdojo_client.py" --action triage

python3 "$SCRIPT_DIR/defectdojo_client.py" \
  --action export \
  --output "$EVIDENCIAS_DIR/defectdojo/defectdojo_consolidated.json"

# ------------------------------------------------------------------------------
# QUALITY GATE B: MODO BLOQUEANTE (EVALUACIÓN ANTE VULNERABILIDADES)
# ------------------------------------------------------------------------------
GATE_MODE="blocking"
if [ "$1" == "--advisory" ]; then
  GATE_MODE="advisory"
fi

echo -e "\n[QUALITY GATE B] Demostración de Quality Gate Pre-producción (Modo: $GATE_MODE)..."
set +e
python3 "$SCRIPT_DIR/quality_gate.py" \
  --mode "$GATE_MODE" \
  --critical 0 \
  --high 0 \
  --medium 10 \
  --semgrep "$EVIDENCIAS_DIR/sast/semgrep_report.json" \
  --trivy-sca "$EVIDENCIAS_DIR/sca/trivy_sca_report.json" \
  --trivy-iac "$EVIDENCIAS_DIR/iac/trivy_iac_report.json" \
  --zap "$EVIDENCIAS_DIR/dast/zap_report.json" \
  | tee "$EVIDENCIAS_DIR/quality_gates/quality_gate_${GATE_MODE}.log"
GATE_EXIT_CODE=$?
set -e

if [ $GATE_EXIT_CODE -ne 0 ]; then
  echo -e "\n[!] DEMOSTRACIÓN EXITOSA DEL REQUISITO 4:"
  echo "    El Quality Gate Bloqueante ha detenido el pipeline con código $GATE_EXIT_CODE."
  echo "    El artefacto no pasa a Producción debido a vulnerabilidades Críticas y Altas detectadas."
else
  echo -e "\n[+] Quality Gate B superado o en modo aviso ($GATE_MODE). Paso a producción autorizado."
fi

echo -e "\n================================================================================"
echo "    PIPELINE DEVSECOPS LOCAL EJECUTADO Y REGISTRADO SATISFACTORIAMENTE          "
echo "================================================================================"
