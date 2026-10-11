FROM node:24.19.0-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43 AS build
WORKDIR /workspace
COPY apps/lab-web/package.json apps/lab-web/package-lock.json ./
RUN npm ci
COPY apps/lab-web/ ./
RUN npm run check && npm run build

FROM nginx:stable-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
COPY infra/containers/nginx.conf /etc/nginx/nginx.conf.template
COPY infra/containers/start-web.sh /usr/local/bin/start-web.sh
COPY --from=build /workspace/dist/ /usr/share/nginx/html/
USER nginx
EXPOSE 8080
ENTRYPOINT ["sh", "/usr/local/bin/start-web.sh"]
