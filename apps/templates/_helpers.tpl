{{/*
Expand the name of the chart.
*/}}
{{- define "sample.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
*/}}
{{- define "sample.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if ne $name .Release.Name -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "sample.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{/*
Return instance and name labels.
*/}}
{{- define "sample.selectorLabels" -}}
app.kubernetes.io/name: {{ include "sample.name" . | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
{{- end }}

{{/*
Return labels, including instance and name.
*/}}
{{- define "sample.labels" -}}
{{ include "sample.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ include "sample.chart" . }}
{{- end }}

{{/*
Return the service account name used by the pod.
*/}}
{{- define "sample.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "sample.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
