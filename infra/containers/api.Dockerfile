FROM eclipse-temurin:21-jdk@sha256:3e3c176ffed168beb42c607be9bc1639b466cf00261a0fb04425562c9d0c5c2b AS build
WORKDIR /workspace
COPY apps/api/ ./
RUN chmod +x mvnw && ./mvnw -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre@sha256:cff19e6215689161eb6162c11b86b0c60ddf802164f2eaf48d570f8fb79a36c5
WORKDIR /app
COPY --from=build /workspace/target/*.jar /app/app.jar
# Stdlib-only exec probe classes; never launch the Spring fat JAR for readiness.
COPY --from=build /workspace/target/classes/io/github/devdooly/platformlab/jobs/runtime/health/ /app/runtime-probe/io/github/devdooly/platformlab/jobs/runtime/health/
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
