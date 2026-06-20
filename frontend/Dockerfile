FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_TURNSTILE_SITE_KEY
ENV VITE_TURNSTILE_SITE_KEY=$VITE_TURNSTILE_SITE_KEY
# Short git commit baked into the bundle so the in-app version badge reflects
# the deployed image. Pass via --build-arg VITE_GIT_SHA=$(git rev-parse --short HEAD).
ARG VITE_GIT_SHA
ENV VITE_GIT_SHA=$VITE_GIT_SHA
RUN npm run build

FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
