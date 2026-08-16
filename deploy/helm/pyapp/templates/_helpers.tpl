{{/* Common naming + labels, so every object in the release is traceable. */}}

{{- define "pyapp.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "pyapp.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{/* Full image reference for a component, e.g. <registry>/api:1.4.0 */}}
{{- define "pyapp.image" -}}
{{- printf "%s/%s:%s" .root.Values.image.registry .component .root.Values.image.tag -}}
{{- end -}}
