# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM node:22-alpine AS deps

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# ── Stage 2: build Next.js ────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Disable Next.js telemetry in CI/build
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 3: lean production runner ───────────────────────────────────────────
# next.config.ts has output: "standalone" — Next.js bundles only what's needed
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs && \
    adduser  --system --uid 1001 nextjs

# Copy the standalone build output (tiny — no node_modules needed)
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER nextjs

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
