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
        skipStagesAfterUnstable()
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10', artifactNumToKeepStr: '5'))
        timestamps()
    }
    // Poll the public main branch; no public Jenkins endpoint/webhook is needed.
    triggers { pollSCM('H/5 * * * *') }
    environment {
        HOME = '/home/jenkins'
        MAVEN_USER_HOME = '/home/jenkins/.m2'
        NPM_CONFIG_CACHE = '/home/jenkins/.cache/npm'
        XDG_CACHE_HOME = '/home/jenkins/.cache'
        ASTRO_TELEMETRY_DISABLED = '1'
        // Dedicated GitHub App: this repository's Commit statuses read/write only.
        // Do not replace it with a developer's existing CLI/OAuth/registry token.
        GITHUB_STATUS_CREDENTIAL_ID = 'platform-lab-github-app'
    }
    stages {
        stage('Checkout') {
            steps {
                script {
                    def scmVars = checkout scm
                    def sourceCommit = scmVars.GIT_COMMIT
                    if (!(sourceCommit ==~ /[0-9a-f]{40}/)) {
                        error('SCM checkout did not return a valid commit SHA')
                    }
                    if (!(scmVars.GIT_BRANCH in ['origin/main', 'main', 'refs/heads/main', 'refs/remotes/origin/main'])) {
                        error('The credentialed publication CI job is restricted to main')
                    }
                    env.SOURCE_COMMIT = sourceCommit
                    writeFile file: 'ci-build-info.txt', text: "sourceCommit=${sourceCommit}\nbuildNumber=${env.BUILD_NUMBER}\n"
                }
            }
        }
        stage('Record pending CI') {
            steps {
                container('node') {
                    withCredentials([usernamePassword(credentialsId: env.GITHUB_STATUS_CREDENTIAL_ID, usernameVariable: 'GITHUB_APP_USERNAME', passwordVariable: 'GITHUB_STATUS_TOKEN')]) {
                        sh label: 'Record pending status for the exact checked-out commit', script: '''#!/bin/sh
set -eu
set +x
CI_STATUS=pending CI_STATUS_OUTPUT=artifacts/jenkins/status-pending.json node infra/scripts/github-commit-status.mjs
'''
                    }
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
        stage('Verify Java example') {
            steps {
                container('maven') {
                    sh label: 'Build and test the independent Java 21 example; do not benchmark in CI', script: '''#!/bin/sh
set -eu
mkdir -p "$MAVEN_USER_HOME"
chmod +x apps/api/mvnw
./apps/api/mvnw -B -ntp -Dmaven.repo.local="$MAVEN_USER_HOME/repository" -f examples/java-window-analysis/pom.xml verify
'''
                }
            }
            post {
                always {
                    junit testResults: 'examples/java-window-analysis/target/surefire-reports/TEST-*.xml', allowEmptyResults: false
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
                    sh label: 'Status client negative tests without credentials', script: 'node --test tests/ci/github-commit-status.test.mjs'
                }
            }
        }
        stage('Archive verified CI') {
            steps {
                container('node') {
                    sh label: 'Require both Java jars, web entry point and exact source metadata', script: '''#!/bin/sh
set -eu
set -- apps/api/target/platform-lab-api-*.jar
test "$#" -eq 1
test -s "$1"
test -s examples/java-window-analysis/target/benchmarks.jar
test -s apps/lab-web/dist/index.html
test -s ci-build-info.txt
test -s artifacts/jenkins/status-pending.json
'''
                }
                archiveArtifacts artifacts: 'apps/api/target/platform-lab-api-*.jar,examples/java-window-analysis/target/benchmarks.jar,apps/lab-web/dist/**,ci-build-info.txt,artifacts/jenkins/status-pending.json', allowEmptyArchive: false, fingerprint: true
            }
        }
        stage('Record success CI') {
            steps {
                container('node') {
                    // Bind only after tests and the required artifacts succeeded.
                    withCredentials([usernamePassword(credentialsId: env.GITHUB_STATUS_CREDENTIAL_ID, usernameVariable: 'GITHUB_APP_USERNAME', passwordVariable: 'GITHUB_STATUS_TOKEN')]) {
                        sh label: 'Confirm tests and artifacts for the exact source SHA', script: '''#!/bin/sh
set -eu
set +x
CI_STATUS=success node infra/scripts/github-commit-status.mjs
'''
                    }
                }
            }
        }
    }
    post {
        unsuccessful {
            script {
                if (env.SOURCE_COMMIT) {
                    container('node') {
                        withCredentials([usernamePassword(credentialsId: env.GITHUB_STATUS_CREDENTIAL_ID, usernameVariable: 'GITHUB_APP_USERNAME', passwordVariable: 'GITHUB_STATUS_TOKEN')]) {
                            withEnv(["CI_STATUS=${currentBuild.currentResult == 'ABORTED' ? 'error' : 'failure'}"]) {
                                sh label: 'Record unsuccessful CI; never publish', script: '''#!/bin/sh
set -eu
set +x
node infra/scripts/github-commit-status.mjs
'''
                            }
                        }
                    }
                }
            }
        }
    }
}
