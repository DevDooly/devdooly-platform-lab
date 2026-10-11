pipeline {
    agent {
        kubernetes {
            inheritFrom 'default'
            yamlFile 'infra/jenkins/agent-pod.yaml'
            yamlMergeStrategy merge()
            defaultContainer 'jnlp'
        }
    }
    options {
        skipDefaultCheckout(true)
        disableConcurrentBuilds()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '5'))
        timestamps()
    }
    environment {
        HOME = '/home/jenkins'
        MAVEN_USER_HOME = '/home/jenkins/.m2'
        NPM_CONFIG_CACHE = '/home/jenkins/.cache/npm'
        XDG_CACHE_HOME = '/home/jenkins/.cache'
        ASTRO_TELEMETRY_DISABLED = '1'
    }
    stages {
        stage('Checkout') {
            steps {
                checkout scm
                script {
                    writeFile file: 'ci-build-info.txt', text: "sourceCommit=${env.GIT_COMMIT ?: 'unknown'}\nbuildNumber=${env.BUILD_NUMBER}\n"
                }
            }
        }
        stage('Verify API') {
            steps {
                container('maven') {
                    dir('apps/api') {
                        sh label: 'Java 21 and Maven Wrapper verification', script: '''#!/bin/sh
set -eu
mkdir -p "$MAVEN_USER_HOME"
java -version
chmod +x mvnw
./mvnw -B -ntp -Dmaven.repo.local="$MAVEN_USER_HOME/repository" verify
'''
                    }
                }
            }
            post {
                always {
                    junit testResults: 'apps/api/target/surefire-reports/TEST-*.xml', allowEmptyResults: false
                }
            }
        }
        stage('Verify web') {
            steps {
                container('node') {
                    dir('apps/lab-web') {
                        sh label: 'Node 24, locked dependencies, tests and static build', script: '''#!/bin/sh
set -eu
mkdir -p "$NPM_CONFIG_CACHE"
node --version
npm --version
npm ci --no-audit --no-fund
npm run check
npm test
npm run build
'''
                    }
                }
            }
        }
    }
    post {
        success {
            archiveArtifacts artifacts: 'apps/api/target/platform-lab-api-*.jar,apps/lab-web/dist/**,ci-build-info.txt', allowEmptyArchive: false, fingerprint: true
        }
    }
}
