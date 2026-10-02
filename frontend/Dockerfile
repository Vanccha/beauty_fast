# Uretim imaji (Next.js). API_URL derleme aninda rewrites'a yazilir;
# calisma aninda da sunucu bilesenleri ayni adresi kullanir.
FROM node:22-alpine AS build
WORKDIR /app
ARG API_URL=http://backend:8000
ENV API_URL=${API_URL} NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --omit=dev

FROM node:22-alpine
WORKDIR /app
ARG API_URL=http://backend:8000
ENV NODE_ENV=production API_URL=${API_URL} NEXT_TELEMETRY_DISABLED=1 PORT=3000
COPY --from=build /app/package.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/next.config.mjs ./
USER node
EXPOSE 3000
CMD ["npx", "next", "start", "-H", "0.0.0.0", "-p", "3000"]
