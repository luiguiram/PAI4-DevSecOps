#!/usr/bin/env bash
# ==============================================================================
# ORQUESTADOR LOCAL DEL PIPELINE DEVSECOPS - INSEGUS ENTERPRISE
# Módulo: run_pipeline_local.sh
# Equipo: Security Team 3 (Grupo 3) - PAI 4 DevSecOps
# Asignatura: Seguridad en Sistemas Informáticos y en Internet
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
APP_DIR="$BASE_DIR/app"
EVIDENCIAS_DIR="$BASE_DIR/evidencias"

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
# ETAPA 2a: ANÁLISIS ESTÁTICO DE CÓDIGO (SAST - SEMGREP)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 2a] Análisis estático de código fuente con Semgrep CE (rulesets oficiales + ST3)..."
docker run --rm \
  -u "$(id -u):$(id -g)" \
  -e HOME=/tmp \
  -v "$BASE_DIR":/workspace \
  -w /workspace \
  semgrep/semgrep semgrep scan \
  --config p/javascript \
  --config p/owasp-top-ten \
  --config /workspace/config/.semgrep.yml \
  --metrics=off \
  --json-output /workspace/evidencias/sast/semgrep_report.json \
  --sarif-output /workspace/evidencias/sast/semgrep_report.sarif \
  /workspace/app || true
echo "[+] Reportes Semgrep generados en evidencias/sast/."

# ------------------------------------------------------------------------------
# ETAPA 2b: ANÁLISIS DE DEPENDENCIAS (SCA - TRIVY)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 2b] Análisis de dependencias de terceros (SCA) con Trivy..."
docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "$BASE_DIR":/workspace \
  aquasec/trivy:latest fs \
  --db-repository ghcr.io/aquasecurity/trivy-db:2 \
  --format json \
  -o /workspace/evidencias/sca/trivy_sca_report.json \
  /workspace/app
echo "[+] Reporte Trivy SCA generado en evidencias/sca/trivy_sca_report.json."

# ------------------------------------------------------------------------------
# ETAPA 2c: ANÁLISIS IaC (TRIVY CONFIG)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 2c] Auditoría de Dockerfile y Manifiestos Kubernetes (IaC) con Trivy..."
docker run --rm \
  -u "$(id -u):$(id -g)" \
  -v "$BASE_DIR":/workspace \
  aquasec/trivy:latest config \
  --format json \
  -o /workspace/evidencias/iac/trivy_iac_report.json \
  /workspace/app
echo "[+] Reporte Trivy IaC generado en evidencias/iac/trivy_iac_report.json."

# ------------------------------------------------------------------------------
# ETAPA 3: QUALITY GATE A (MODO AVISO)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 3 - QUALITY GATE A] Evaluación de Quality Gate A en Modo Aviso..."
python3 "$SCRIPT_DIR/quality_gate.py" \
  --mode advisory \
  --semgrep "$EVIDENCIAS_DIR/sast/semgrep_report.json" \
  --trivy-sca "$EVIDENCIAS_DIR/sca/trivy_sca_report.json" \
  --trivy-iac "$EVIDENCIAS_DIR/iac/trivy_iac_report.json" \
  | tee "$EVIDENCIAS_DIR/quality_gates/quality_gate_warning_mode.log"
echo "[+] Quality Gate A evaluado (no bloqueante, continue-on-error: true)."

# ------------------------------------------------------------------------------
# ETAPA 4: DESPLIEGUE EN STAGING Y DAST REAL (OWASP ZAP FULL SCAN)
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 4] Despliegue en Staging y Análisis Dinámico real con OWASP ZAP..."
(
  cd "$APP_DIR"
  docker compose up -d --build
)
trap '(cd "$APP_DIR" && docker compose down) || true' EXIT

for i in $(seq 1 30); do
  if curl -sf http://localhost:3000/health | grep -q "UP"; then
    echo "[+] Servicio Staging disponible en http://localhost:3000."
    break
  fi
  sleep 2
done

ZAP_WRK_DIR=$(mktemp -d)
chmod 777 "$ZAP_WRK_DIR"
cp "$BASE_DIR/config/zap-baseline.conf" "$ZAP_WRK_DIR/zap.conf"
docker run --rm --network host \
  -v "$ZAP_WRK_DIR":/zap/wrk:rw \
  ghcr.io/zaproxy/zaproxy:stable zap-full-scan.py \
  -t http://localhost:3000 \
  -c zap.conf \
  -m 2 -T 5 \
  -J zap_report.json \
  -x zap_report.xml \
  -r zap_report.html || true
cp "$ZAP_WRK_DIR/zap_report.json" "$EVIDENCIAS_DIR/dast/zap_report.json"
cp "$ZAP_WRK_DIR/zap_report.xml" "$EVIDENCIAS_DIR/dast/zap_report.xml"
cp "$ZAP_WRK_DIR/zap_report.html" "$EVIDENCIAS_DIR/dast/zap_report.html"
rm -rf "$ZAP_WRK_DIR"

(
  cd "$APP_DIR"
  docker compose down
)
trap - EXIT
echo "[+] Reportes reales OWASP ZAP generados en evidencias/dast/ (JSON, XML y HTML)."

# ------------------------------------------------------------------------------
# ETAPA 5: CENTRALIZACIÓN Y TRIAJE EN DEFECTDOJO API v2
# ------------------------------------------------------------------------------
echo -e "\n[ETAPA 5] Ingesta y consolidación en DefectDojo API v2..."
rm -f "$EVIDENCIAS_DIR/defectdojo/defectdojo_findings_db.json"
python3 "$SCRIPT_DIR/defectdojo_client.py" \
  --action import \
  --semgrep "$EVIDENCIAS_DIR/sast/semgrep_report.json" \
  --trivy-sca "$EVIDENCIAS_DIR/sca/trivy_sca_report.json" \
  --trivy-iac "$EVIDENCIAS_DIR/iac/trivy_iac_report.json" \
  --zap "$EVIDENCIAS_DIR/dast/zap_report.xml"

python3 "$SCRIPT_DIR/defectdojo_client.py" --action triage

python3 "$SCRIPT_DIR/defectdojo_client.py" \
  --action export \
  --output "$EVIDENCIAS_DIR/defectdojo/defectdojo_consolidated.json"

# ------------------------------------------------------------------------------
# ETAPA 6: QUALITY GATE B (MODO BLOQUEANTE SOBRE DEFECTDOJO POST-TRIAJE)
# ------------------------------------------------------------------------------
GATE_MODE="blocking"
if [ "${1:-}" == "--advisory" ]; then
  GATE_MODE="advisory"
fi

echo -e "\n[ETAPA 6 - QUALITY GATE B] Evaluación pre-producción (Modo: $GATE_MODE)..."
set +e
python3 "$SCRIPT_DIR/quality_gate.py" \
  --mode "$GATE_MODE" \
  --critical 0 \
  --high 0 \
  --medium 10 \
  --defectdojo-report "$EVIDENCIAS_DIR/defectdojo/defectdojo_consolidated.json" \
  | tee "$EVIDENCIAS_DIR/quality_gates/quality_gate_${GATE_MODE}.log"
GATE_EXIT_CODE=${PIPESTATUS[0]}
set -eo pipefail

if [ "$GATE_EXIT_CODE" -ne 0 ]; then
  echo -e "\n[!] Quality Gate B ha detenido el pipeline con código $GATE_EXIT_CODE."
  exit "$GATE_EXIT_CODE"
else
  echo -e "\n[+] Quality Gate B superado ($GATE_MODE). Paso a producción autorizado."
fi
