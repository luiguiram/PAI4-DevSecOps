# ==============================================================================
# INSEGUS Enterprise Dockerfile - Hardened Production Container (IaC Secure)
# Security Team 3 - PAI 4 DevSecOps
# ==============================================================================
FROM node:22-alpine

WORKDIR /app

COPY --chown=node:node package*.json ./

RUN npm install --omit=dev --ignore-scripts

COPY --chown=node:node . .

ENV NODE_ENV=production
ENV PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:3000/health || exit 1

USER node

CMD ["node", "server.js"]
