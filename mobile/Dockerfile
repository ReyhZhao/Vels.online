# Builds the Expo update bundle (Hermes bytecode for iOS + Android and its
# metadata) and serves it via nginx — the self-hosted OTA update artifact the
# installed apps pull instead of waiting for a store release.
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV CI=1
RUN npx expo export --platform ios --platform android

FROM nginx:alpine AS production
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
