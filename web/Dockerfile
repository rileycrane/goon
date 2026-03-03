FROM node:20-slim AS builder

WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
ENV NEXT_PUBLIC_API_URL=https://api.holdplz.ai
RUN npm run build

FROM node:20-slim AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
