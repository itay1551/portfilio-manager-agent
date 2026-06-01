# Stage 1: build (Red Hat UBI — avoids Docker Hub auth in restricted environments)
FROM registry.access.redhat.com/ubi9/nodejs-20 AS build

USER 0
WORKDIR /app

ARG VITE_ORCHESTRATOR_URL=/api/chat
ARG VITE_OPENAI_API_ENDPOINT=
ARG VITE_OPENAI_API_TOKEN=
ARG VITE_OPENAI_MODEL=

ENV VITE_ORCHESTRATOR_URL=$VITE_ORCHESTRATOR_URL
ENV VITE_OPENAI_API_ENDPOINT=$VITE_OPENAI_API_ENDPOINT
ENV VITE_OPENAI_API_TOKEN=$VITE_OPENAI_API_TOKEN
ENV VITE_OPENAI_MODEL=$VITE_OPENAI_MODEL

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# Stage 2: serve
FROM registry.access.redhat.com/ubi9/nginx-120

USER 0
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
RUN chgrp -R 0 /usr/share/nginx/html && chmod -R g+rwX /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
