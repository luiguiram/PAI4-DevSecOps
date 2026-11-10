# ==============================================================================
# INSEGUS Enterprise Dockerfile - Pipeline Testbed (IaC Misconfigurations)
# Security Team 3 - PAI 4 DevSecOps
# ==============================================================================
FROM node:16-alpine

# VULNERABILIDAD IaC #1: Ejecución como usuario root (falta directiva USER)
# No se especifica un usuario no privilegiado (e.g. node / appuser)

WORKDIR /app

# Copia de artefactos sin exclusión adecuada
COPY package*.json ./

# Instalación sin verificación estricta de lockfile
RUN npm install --legacy-peer-deps

COPY . .

# VULNERABILIDAD IaC #2: Variables de entorno inseguras y puertos expuestos
ENV NODE_ENV=development
ENV PORT=3000
ENV DEBUG=*

# VULNERABILIDAD IaC #3: Falta directiva HEALTHCHECK y permisos excesivos en directorio
RUN chmod -R 777 /app

EXPOSE 3000

CMD ["node", "server.js"]
