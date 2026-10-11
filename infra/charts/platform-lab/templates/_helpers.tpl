{{- define "platform-lab.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 54 | trimSuffix "-" -}}
{{- end -}}

{{- define "platform-lab.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "platform-lab.labels" -}}
{{ include "platform-lab.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | quote }}
{{- end -}}

{{- define "platform-lab.image" -}}
{{- $repository := required "image.repository is required; API/web images are not published yet" .repository -}}
{{- $digest := required "image.digest is required; use a published sha256 digest" .digest -}}
{{- if .tag -}}
{{- printf "%s:%s@%s" $repository .tag $digest -}}
{{- else -}}
{{- printf "%s@%s" $repository $digest -}}
{{- end -}}
{{- end -}}