# Multi-Agent Customer Support Crew — frontend (Next.js)
# Build from frontend/: docker build -t bmobile-support-frontend .
# For compose, NEXT_PUBLIC_API_BASE_URL should point at the backend service
# (e.g. http://backend:8001) so server-side rewrites/proxies reach CrewAI.

FROM node:20-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Next.js expects public/; this repo may omit it — create empty dir for COPY.
RUN mkdir -p public

# Server-side proxy target inside the compose network (rewrites + route handlers).
ARG NEXT_PUBLIC_API_BASE_URL=http://backend:8001
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN npm run build

FROM node:20-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    PORT=3000 \
    NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE_URL=http://backend:8001

COPY --from=builder /app/package.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./
COPY --from=builder /app/tsconfig.json ./

EXPOSE 3000

CMD ["npm", "run", "start"]
