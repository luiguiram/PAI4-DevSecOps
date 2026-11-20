# PAI 4: Pipeline DevSecOps — Aseguramiento de la Cadena de Suministro en Aplicaciones Web

**Equipo:** Security Team 3 (Grupo 3)  
**Integrantes:** Kleber Leonardo de Carvalho, Paula Benítez, Luigui Juan Guillermo Ramos  
**Asignatura:** Seguridad en Sistemas Informáticos y en Internet (Curso 2026/2027)  
**Centro:** E.T.S. Ingeniería Informática — Universidad de Sevilla  
**Repositorio:** [https://github.com/luiguiram/PAI4-DevSecOps](https://github.com/luiguiram/PAI4-DevSecOps)

---

## 1. Descripción General del Proyecto

Este proyecto implementa un pipeline **DevSecOps** (*Security as Code*) para el caso práctico de **INSEGUS**, orientado a mitigar vulnerabilidades en el desarrollo y despliegue de aplicaciones web basadas en microservicios contenerizados sobre Kubernetes.

El pipeline automatiza las comprobaciones de seguridad en cada `push` o `pull_request` sobre la rama principal bajo un enfoque **Shift Left**, integrando pruebas estáticas, análisis de dependencias, auditoría de infraestructura como código, pruebas dinámicas en entorno de *staging*, centralización de hallazgos y *Quality Gates* diferenciados.

---

## 2. Arquitectura del Pipeline y Herramientas Integradas

El flujo automatizado en [`.github/workflows/devsecops-pipeline.yml`](.github/workflows/devsecops-pipeline.yml) cubre cuatro categorías de análisis de seguridad y una plataforma centralizada de gestión de vulnerabilidades:

| Tipo de Prueba | Herramienta | Alcance y Detección | Salida Generada |
| :--- | :--- | :--- | :--- |
| **SAST** (Análisis Estático) | **Semgrep CE** | Inyecciones SQL (`CWE-89`), uso de `eval()` (`CWE-95`), credenciales hardcodeadas (`CWE-798`) y CORS permisivo (`CWE-942`). | `evidencias/sast/semgrep_report.json` y `.sarif` |
| **SCA** (Dependencias) | **Trivy Dependencies** | Vulnerabilidades conocidas (CVE) en librerías directas y transitivas declaradas en `app/package-lock.json`. | `evidencias/sca/trivy_sca_report.json` |
| **IaC** (Infraestructura) | **Trivy Config** | Desconfiguraciones en `app/Dockerfile` (usuario `root`, sin `HEALTHCHECK`) y manifiestos de Kubernetes (`privileged: true`, `SYS_ADMIN`, `hostNetwork`). | `evidencias/iac/trivy_iac_report.json` |
| **DAST** (Análisis Dinámico) | **OWASP ZAP** | Escaneo pasivo (*Baseline*) y pruebas activas sobre el contenedor desplegado en *staging* (`http://localhost:3000`): SQLi, XSS reflejado, SSRF y cabeceras HTTP. | `evidencias/dast/zap_report.json` y `.html` |
| **Gestión de Vulnerabilidades** | **DefectDojo (API v2)** | Ingesta automatizada, deduplicación por hash SHA-256, priorización (P1–P4) y registro de triaje / falsos positivos. | `evidencias/defectdojo/defectdojo_consolidated.json` |

---

## 3. Política de Quality Gates

El pipeline implementa dos *Quality Gates* con comportamiento diferenciado para permitir la evaluación completa de la aplicación vulnerable en *staging* sin comprometer la seguridad de producción:

1. **Quality Gate A — Modo Aviso (*Advisory*, etapa de Build / Análisis Estático):**
   - Configurado con `continue-on-error: true`.
   - Evalúa los informes de SAST, SCA e IaC y registra las advertencias en el flujo sin abortar la ejecución, permitiendo el despliegue posterior en *staging* para ejecutar las pruebas dinámicas (DAST).
2. **Quality Gate B — Modo Bloqueante (*Blocking*, etapa Pre-Producción):**
   - Configurado con tolerancia cero para vulnerabilidades **Críticas (`> 0`)**, **Altas (`> 0`)** y límite de **Medias (`> 10`)**.
   - Al superarse cualquiera de los umbrales tras la consolidación en DefectDojo, el evaluador [`scripts/quality_gate.py`](scripts/quality_gate.py) finaliza con código de salida `1` (`exit 1`), deteniendo el pipeline e impidiendo el despliegue a producción.

---

## 4. Estructura del Repositorio

```text
.
├── .github/workflows/
│   └── devsecops-pipeline.yml        # Definición principal del pipeline en GitHub Actions
├── app/                              # Microservicio web vulnerable (Node.js/Express + Docker + K8s)
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── kubernetes/
│   ├── public/
│   ├── package.json
│   └── server.js
├── config/                           # Reglas y políticas de las herramientas de seguridad
│   ├── .semgrep.yml
│   ├── trivy.yaml
│   ├── zap-baseline.conf
│   └── quality_gate_policy.json
├── evidencias/                       # Diagramas, capturas, informes de escáneres, logs y DefectDojo
│   ├── capturas/                     # Capturas reales de ejecuciones CI/CD y DefectDojo (PNG)
│   ├── diagramas/
│   ├── sast/
│   ├── sca/
│   ├── iac/
│   ├── dast/
│   ├── quality_gates/
│   ├── pipeline_logs/
│   └── defectdojo/
├── scripts/                          # Scripts de automatización, DAST, DefectDojo y Quality Gates
│   ├── run_pipeline_local.sh
│   ├── quality_gate.py
│   ├── defectdojo_client.py
│   ├── mock_defectdojo.py
│   └── run_zap_dast.py
├── INFORME-PAI4-ST3.md               # Fuente Markdown del informe técnico
├── INFORME-PAI4-ST3.pdf              # Informe técnico oficial en PDF
└── generate_pdf.py                   # Generador automático del informe PDF
```

---

## 5. Verificación y Ejecución Local

Requisitos previos: `docker`, `python3` y `node`.

### 5.1. Ejecución completa del pipeline local
```bash
./scripts/run_pipeline_local.sh
```
Este script ejecuta los tests unitarios, los análisis con Semgrep y Trivy en Docker, la evaluación del Quality Gate A en modo aviso, el despliegue local de la aplicación con el análisis DAST, la sincronización y triaje en DefectDojo y finalmente la verificación bloqueante del Quality Gate B.

### 5.2. Comprobación individual de los Quality Gates
- **Evaluación en modo bloqueante (retorna código de salida `1` ante vulnerabilidades críticas/altas):**
  ```bash
  python3 scripts/quality_gate.py \
    --mode blocking \
    --critical 0 \
    --high 0 \
    --medium 10 \
    --semgrep evidencias/sast/semgrep_report.json \
    --trivy-sca evidencias/sca/trivy_sca_report.json \
    --trivy-iac evidencias/iac/trivy_iac_report.json \
    --zap evidencias/dast/zap_report.json
  ```
- **Evaluación en modo aviso (retorna código de salida `0`):**
  ```bash
  python3 scripts/quality_gate.py \
    --mode advisory \
    --semgrep evidencias/sast/semgrep_report.json \
    --trivy-sca evidencias/sca/trivy_sca_report.json \
    --trivy-iac evidencias/iac/trivy_iac_report.json \
    --zap evidencias/dast/zap_report.json
  ```

### 5.3. Diagramas de Diseño y Documentación
- **Diagrama 1.a (Pipeline DevSecOps):** [`evidencias/diagramas/pipeline_devsecops_diagram.svg`](evidencias/diagramas/pipeline_devsecops_diagram.svg)
- **Diagrama 1.b (Flujo ante una vulnerabilidad):** [`evidencias/diagramas/vulnerability_flowchart_diagram.svg`](evidencias/diagramas/vulnerability_flowchart_diagram.svg)
- **Informe técnico completo:** [`INFORME-PAI4-ST3.pdf`](INFORME-PAI4-ST3.pdf) (recompilable mediante `python3 generate_pdf.py`).

---

## 6. Política de Seguridad y Credenciales

Todas las credenciales sensibles (como `DEFECTDOJO_URL` y `DEFECTDOJO_API_KEY`) se referencian exclusivamente mediante secretos del servidor CI/CD (`${{ secrets.* }}`). No existe ninguna credencial ni clave real almacenada en los ficheros del repositorio.
