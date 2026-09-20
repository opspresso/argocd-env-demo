{{/*
Allow an explicit resources: null to omit Kubernetes requests and limits.
Keep upstream normalization and validation whenever resources are configured.
*/}}
{{- define "neo4j.checkResources" -}}
  {{- if .Values.neo4j.resources -}}
    {{- template "neo4j.resources.checkForEmptyResources" . -}}
    {{- template "neo4j.resources.evaluateCPU" . -}}
    {{- template "neo4j.resources.evaluateMemory" . -}}
  {{- end -}}
{{- end -}}
