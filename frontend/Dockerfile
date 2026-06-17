# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM node:24-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install --omit=dev

# ── Stage 2: build Next.js ────────────────────────────────────────────────────
FROM node:24-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install

COPY . .

# Ensure public/ exists (Next.js projects may omit it)
RUN mkdir -p /app/public

# Disable Next.js telemetry in CI/build
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 3: lean production runner ───────────────────────────────────────────
# next.config.ts has output: "standalone" — Next.js bundles only what's needed
FROM node:24-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# Copy the standalone build output — chown ensures nextjs user can write wasm cache
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

# Pre-create the wasm fallback dir so nextjs user can write SWC cache at runtime
RUN mkdir -p /app/node_modules/next/wasm && \
    chown -R nextjs:nodejs /app/node_modules/next/wasm

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
