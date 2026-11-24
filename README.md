# PAI 4: Pipeline DevSecOps — Aseguramiento de la Cadena de Suministro en Aplicaciones Web

**Equipo:** Security Team 3 (Grupo 3)  
**Integrantes:** Kleber Leonardo de Carvalho, Paula Benítez, Luigui Juan Guillermo Ramos  
**Asignatura:** Seguridad en Sistemas Informáticos y en Internet (Curso 2026/2027)  
**Centro:** E.T.S. Ingeniería Informática — Universidad de Sevilla  
**Repositorio:** [https://github.com/luiguiram/PAI4-DevSecOps](https://github.com/luiguiram/PAI4-DevSecOps)

---

## 1. Descripción General del Proyecto

Este proyecto implementa un pipeline **DevSecOps** (*Security as Code*) para el caso práctico de **INSEGUS**, orientado a detectar y bloquear vulnerabilidades en el ciclo de vida de microservicios web Node.js contenerizados sobre Kubernetes.

El workflow [`.github/workflows/devsecops-pipeline.yml`](.github/workflows/devsecops-pipeline.yml) automatiza **7 etapas (9 jobs)** reales con ejecución demostrada tanto en fallo por *Quality Gate* ([Run #23 en `main`](https://github.com/luiguiram/PAI4-DevSecOps/actions/runs/45365338199)) como en aprobación y despliegue a producción tras remediación ([Run #24 en `demo/remediacion-gate-b-verde`](https://github.com/luiguiram/PAI4-DevSecOps/actions/runs/45368752719)).

---

## 2. Arquitectura del Pipeline y Herramientas Integradas

| Etapa / Tipo de Prueba | Herramienta | Alcance y Detección Real | Salida Generada |
| :--- | :--- | :--- | :--- |
| **1. Build & Tests** | **Node.js `node --test`** | Instalación de dependencias (`--ignore-scripts`) y 8 pruebas unitarias funcionales en `app/tests/server.test.js`. | Resumen en CI |
| **2a. SAST** | **Semgrep CE** | Rulesets oficiales (`p/javascript`, `p/owasp-top-ten`) + reglas propias (`config/.semgrep.yml`) sobre código fuente, Dockerfile y Kubernetes (109 reglas). | `evidencias/sast/semgrep_report.json` y `.sarif` |
| **2b. SCA** | **Trivy Dependencies** | Escaneo `fs` de árbol completo de dependencias directas y transitivas en `app/package-lock.json`. | `evidencias/sca/trivy_sca_report.json` |
| **2c. IaC** | **Trivy Config** | Auditoría CIS/Rego sobre `app/Dockerfile` y `app/kubernetes/*.yaml`. | `evidencias/iac/trivy_iac_report.json` |
| **3. Gate A (Aviso)** | `scripts/quality_gate.py` | Evalúa reportes estáticos (`continue-on-error: true`), avisa sin abortar para habilitar *staging*. | Resumen en CI |
| **4. Staging & DAST** | **OWASP ZAP (`zap-full-scan.py`)** | Contenedor en `http://localhost:3000` auditado con *spider* y escaneo activo real (SQLi, XSS, SSRF, RFI, CORS, cabeceras). | `evidencias/dast/zap_report.xml`, `.json`, `.html` |
| **5. DefectDojo (API v2)** | **OWASP DefectDojo real** | Despliegue efímero real en CI (si no hay secretos externos), ingesta con `--strict-api`, deduplicación SHA-256 y triaje de falso positivo CORS. | `evidencias/defectdojo/defectdojo_consolidated.json` |
| **6. Gate B (Bloqueante)** | `scripts/quality_gate.py` | Evalúa **activos post-triaje de DefectDojo** (`0 Crít / 0 Altas / ≤ 10 Medias`): `exit 1` en `main` / `exit 0` en rama remediada. | Autorización o bloqueo de Etapa 7 |
| **7. Deploy Producción** | **Kubernetes (`insegus-production`)** | Despliegue continuo ejecutado únicamente si Gate B retorna `exit 0`. | `evidencias/pipeline_logs/pipeline_success_green_run24.log` |

---

## 3. Demostración Dual de Quality Gates (Rojo vs. Verde)

- **Rama `main` (microservicio intencionadamente vulnerable — [Run `#23`](https://github.com/luiguiram/PAI4-DevSecOps/actions/runs/45365338199)):**  
  Etapas 1–5 en verde (DefectDojo real consolida 144 hallazgos y tria 1 falso positivo → **143 activos**: 3 Críticas, 64 Altas, 48 Medias, 24 Bajas, 4 Info). **Gate B bloquea con `exit 1`** y Etapa 7 queda `skipped`.
- **Rama `demo/remediacion-gate-b-verde` (código/dependencias/IaC remediados — [Run `#24`](https://github.com/luiguiram/PAI4-DevSecOps/actions/runs/45368752719)):**  
  SAST=0, SCA=0, IaC=0 Crít/Altas (1 Media), DAST=0 Crít/Altas (1 Media). **Gate B aprueba con `exit 0`** (0 Críticas, 0 Altas, 2 Medias) y **Etapa 7 (`7. Deploy Producción`) finaliza en verde**.

---

## 4. Estructura del Repositorio

```text
.
├── .github/workflows/
│   └── devsecops-pipeline.yml        # Definición oficial (7 etapas / 9 jobs reales)
├── app/                              # Microservicio web Node.js + Dockerfile + K8s + tests
├── config/                           # Reglas .semgrep.yml, trivy.yaml, zap-baseline.conf, policy
├── evidencias/
│   ├── artefactos_run23/             # Artefactos oficiales del Run #23 (main, Gate B rojo)
│   ├── artefactos_run24_verde/       # Artefactos oficiales del Run #24 (rama remediada verde)
│   ├── capturas/                     # Capturas reales de GitHub Actions y DefectDojo
│   ├── diagramas/                    # Diagramas SVG (1.a y 1.b)
│   ├── sast/ · sca/ · iac/ · dast/   # Informes reales más recientes (Semgrep, Trivy, ZAP)
│   ├── quality_gates/                # Logs reales de Gate A y Gate B (aviso, rojo y verde)
│   ├── pipeline_logs/                # Resúmenes completos de ejecución CI
│   └── defectdojo/                   # defectdojo_consolidated.json real API v2 y log CI
├── scripts/
│   ├── run_pipeline_local.sh         # Orquestador local (Semgrep, Trivy, ZAP Full Scan, Gate)
│   ├── quality_gate.py               # Evaluador Gate A / Gate B (lee DefectDojo post-triaje)
│   ├── defectdojo_client.py          # Cliente REST API v2 real (--strict-api en CI)
│   └── mock_defectdojo.py            # Backend offline exclusivamente para ejecución local sin Docker DefectDojo
├── INFORME-PAI4-ST3.md               # Fuente Markdown de la memoria técnica
├── INFORME-PAI4-ST3.pdf              # Memoria técnica oficial (≤ 15 págs. cuerpo técnico)
└── generate_pdf.py                   # Compilador PDF mediante Chromium/Brave headless
```

---

## 5. Verificación y Ejecución Local

Requisitos previos: `docker`, `python3`, `node` y `npm`.

```bash
# Ejecutar tests unitarios
cd app && npm install --legacy-peer-deps --ignore-scripts && npm test && cd ..

# Ejecutar pipeline local completo (Semgrep, Trivy, OWASP ZAP Full Scan, DefectDojo y Gate B)
./scripts/run_pipeline_local.sh

# Comprobar Gate B directamente contra el resumen consolidado de DefectDojo real
python3 scripts/quality_gate.py \
  --mode blocking \
  --critical 0 --high 0 --medium 10 \
  --defectdojo-report evidencias/defectdojo/defectdojo_consolidated.json
```

### Documentación y Diagramas
- **Diagrama 1.a (Arquitectura del Pipeline):** [`evidencias/diagramas/pipeline_devsecops_diagram.svg`](evidencias/diagramas/pipeline_devsecops_diagram.svg)
- **Diagrama 1.b (Flujo ante una Vulnerabilidad):** [`evidencias/diagramas/vulnerability_flowchart_diagram.svg`](evidencias/diagramas/vulnerability_flowchart_diagram.svg)
- **Informe Técnico:** [`INFORME-PAI4-ST3.pdf`](INFORME-PAI4-ST3.pdf) (recompilable con `python3 generate_pdf.py`)

---

## 6. Política de Seguridad y Credenciales

Todas las credenciales sensibles (`DEFECTDOJO_URL`, `DEFECTDOJO_API_KEY`) se inyectan vía secretos de GitHub Actions (`${{ secrets.* }}`) o se generan dinámicamente en memoria durante el despliegue efímero de DefectDojo en CI con enmascaramiento (`::add-mask::`). No existe ninguna credencial real almacenada en el repositorio.
