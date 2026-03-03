FROM node:20-slim AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ENV NEXT_PUBLIC_API_URL=https://api.holdplz.ai
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public 2>/dev/null || true

EXPOSE 3000
CMD ["node", "server.js"]
