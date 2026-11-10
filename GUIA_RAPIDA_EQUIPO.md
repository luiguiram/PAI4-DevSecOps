# GUÍA RÁPIDA DEL PROYECTO DEVSECOPS - PAI 4 (INSEGUS)
### Security Team 3 (Grupo 3) — Universidad de Sevilla
**Repositorio Oficial:** [https://github.com/luiguiram/PAI4-DevSecOps](https://github.com/luiguiram/PAI4-DevSecOps) (Público)  
**Autores:** Kleber Leonardo de Carvalho, Paula Benítez, Luigui Juan, Guillermo Ramos  
**Asignatura:** Seguridad en Sistemas Informáticos y en Internet (Curso 2026/2027)  

---

## 1. ¿De qué va este PAI 4 y qué hemos hecho?

El cliente de INSEGUS sufrió incidentes graves de seguridad porque su pipeline de integración continua compilaba y desplegaba a producción sin comprobar la seguridad en ningún momento (código con fallos, librerías con CVEs y contenedores ejecutándose como root).

Nosotros hemos transformado ese pipeline tradicional en un **Pipeline DevSecOps** (*Security as Code*) completamente automatizado:
1. **Analizamos la seguridad en 4 capas distintas**: código fuente propio, librerías de terceros, infraestructura (Docker y Kubernetes) y la aplicación en ejecución.
2. **Configuramos dos compuertas (*Quality Gates*)**:
   - **Gate A (en compilación):** Modo aviso (`continue-on-error: true`). Te informa de los fallos pero deja continuar, para poder desplegar el contenedor de pruebas.
   - **Gate B (antes de producción):** Modo bloqueante. Si hay vulnerabilidades **Críticas o Altas**, el pipeline **se detiene con error (`exit 1`)** y bloquea la entrega a producción.
3. **Centralizamos todo en DefectDojo**: Los informes llegan solos por API REST v2, se eliminan duplicados y se gestionan los falsos positivos.

---

## 2. Las 4 herramientas que hemos integrado

| Tipo de prueba | Herramienta | ¿Qué busca exactamente? | Informe generado |
| :--- | :--- | :--- | :--- |
| **SAST** (Código estático) | **Semgrep** | Inyecciones SQL (`$DB.get`), funciones peligrosas (`eval()`) y contraseñas/secretos JWT escritos a fuego en el código. | `evidencias/sast/semgrep_report.json` |
| **SCA** (Dependencias) | **Trivy** | Librerías de terceros en `package.json` con vulnerabilidades conocidas públicamente (CVEs en `axios`, `lodash`, etc.). | `evidencias/sca/trivy_sca_report.json` |
| **IaC** (Infraestructura) | **Trivy Config** | Fallos en el `Dockerfile` (correr como `root`) y en los manifiestos de Kubernetes (`SYS_ADMIN`, modo privilegiado). | `evidencias/iac/trivy_iac_report.json` |
| **DAST** (Dinámico) | **OWASP ZAP** | Ataca la aplicación en marcha (`http://localhost:3000`) para ver si de verdad se puede hacer bypass en el login con SQLi, inyectar XSS o hacer peticiones internas (SSRF). | `evidencias/dast/zap_report.json` |
| **Gestión** | **DefectDojo API** | Recibe todos los informes por API REST v2, unifica los 103 hallazgos, elimina repetidos y documenta falsos positivos. | `evidencias/defectdojo/defectdojo_consolidated.json` |

---

## 3. La clave que os preguntará el profesor: ¿Por qué dos Quality Gates?

> **Pregunta típica de defensa:** *«¿Por qué no bloqueáis el pipeline directamente en el primer fallo de código?»*  
> **Respuesta del equipo:** *«Porque la aplicación es vulnerable a propósito. Si bloqueamos en la etapa de Build, el pipeline abortaría de inmediato y **nunca llegaríamos a levantar el contenedor de Staging para probar el DAST (OWASP ZAP)**. Por eso, el **Gate A está en modo aviso** (permite continuar con `continue-on-error: true`), mientras que el **Gate B es el bloqueante real** antes del paso a producción (tolerancia cero a críticas/altas).»*

---

## 4. Guía práctica: Cómo comprobar el funcionamiento (Paso a Paso)

Abrid una terminal en la carpeta del proyecto:
```bash
cd [la ubicación del proyecto]
```

### Paso 1: Ejecutar el pipeline completo de principio a fin
Lanzad el script orquestador:
```bash
./scripts/run_pipeline_local.sh
```
**¿Qué veréis que ocurre en pantalla?**
1. Ejecuta los tests unitarios de Node.js.
2. Lanza **Semgrep** en Docker y detecta los secretos y la inyección SQL en el código.
3. Lanza **Trivy** y detecta las vulnerabilidades en los paquetes npm y las desconfiguraciones del Dockerfile y Kubernetes.
4. Evalúa el **Quality Gate A (Modo Aviso)**: muestra las advertencias y **sigue adelante sin pararse**.
5. Levanta el microservicio en `http://localhost:3000` y lanza el análisis **DAST con OWASP ZAP** (confirmando el bypass del login y XSS).
6. Envía todos los informes a **DefectDojo** vía API, deduplica los hallazgos y marca un falso positivo justificado (regla CORS).
7. Evalúa el **Quality Gate B (Modo Bloqueante)**: detecta 3 críticas y 72 altas, **falla con código `exit 1` y bloquea la entrega a producción**.

---

### Paso 2: Comprobar el bloqueo del Quality Gate
Para demostrar que el Quality Gate B realmente detiene el pipeline ante vulnerabilidades:
```bash
python3 scripts/quality_gate.py \
  --mode blocking \
  --critical 0 \
  --high 0 \
  --semgrep evidencias/sast/semgrep_report.json \
  --trivy-sca evidencias/sca/trivy_sca_report.json \
  --trivy-iac evidencias/iac/trivy_iac_report.json \
  --zap evidencias/dast/zap_report.json
```
Comprobad el código de salida que devuelve en bash:
```bash
echo $?
```
Devolverá `1` (*fallo / pipeline abortado*).

Si lo ejecutáis en modo aviso (`--mode advisory`), veréis que devuelve `0` (*continúa*):
```bash
python3 scripts/quality_gate.py --mode advisory --semgrep evidencias/sast/semgrep_report.json --trivy-sca evidencias/sca/trivy_sca_report.json --trivy-iac evidencias/iac/trivy_iac_report.json --zap evidencias/dast/zap_report.json
echo $? # Imprime 0
```

---

### Paso 3: Ver las trazas y evidencias generadas
Todos los resultados generados están guardados y listos para consultar:
- **Trazas de ejecución de los Gates:** en `evidencias/quality_gates/`
- **Logs de fallo bloqueante del pipeline:** `evidencias/pipeline_logs/pipeline_failure_quality_gate.log`
- **Diagramas de diseño:** en `evidencias/diagramas/`
  - `pipeline_devsecops_diagram.svg` (Diagrama 1.a)
  - `vulnerability_flowchart_diagram.svg` (Diagrama 1.b)
  - `defectdojo_dashboard.svg` (Dashboard de métricas)

---

### Paso 4: Cómo recompilar el informe PDF oficial si editáis algo
El informe está escrito en Markdown en `INFORME-PAI4-ST3.md`. Si retocáis alguna frase o autor, para compilar el PDF oficial simplemente ejecutad:
```bash
python3 generate_pdf.py
```
El script generará `INFORME-PAI4-ST3.pdf`, comprobando que el cuerpo técnico del informe no exceda el límite de **15 páginas** (actualmente ocupa exactamente 11 páginas de contenido central, más portada y anexos de evidencias).

---

## 5. ¿Qué archivo se entrega en la Enseñanza Virtual?

El archivo que tenéis que subir a la plataforma de la Universidad es:
📦 **`PAI4-ST3.zip`** (ubicado directamente en `/home/thespace81/Documentos/SSII/PAI4/PAI4-ST3.zip`).

Dentro contiene todo lo que exigen las normas del entregable:
1. El informe en PDF institucional (`INFORME-PAI4-ST3.pdf`).
2. Los flujos de CI/CD (`.github/workflows/devsecops-pipeline.yml` y `.gitlab-ci.yml`).
3. El código del microservicio vulnerable y manifiestos de Kubernetes (`app/`).
4. Las configuraciones de las herramientas (`config/`).
5. Los scripts de Quality Gates y DefectDojo (`scripts/`).
6. Todas las evidencias técnicas y logs con el fallo bloqueante por Quality Gate (`evidencias/`).
7. **Cero credenciales en código**, cumpliendo estrictamente con la penalización de seguridad.
