# argocd-env-demo

* <https://github.com/argoproj/argo-cd>

```bash
export TG_USERNAME="nalbam"
export TG_PROJECT="sample-dov"
export TG_VERSION="v0.0.0"
export TG_PHASE="demo"
export TG_TYPE="helm"

./build.sh
```

## github action repository_dispatch

```bash
PAYLOAD="{\"event_type\":\"gitops\","
PAYLOAD="${PAYLOAD}\"client_payload\":{"
PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
PAYLOAD="${PAYLOAD}\"phase\":\"${TG_PHASE}\","
PAYLOAD="${PAYLOAD}\"type\":\"${TG_TYPE}\""
PAYLOAD="${PAYLOAD}}}"

curl -sL -X POST \
  -H "Accept: application/vnd.github.v3+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -d "${PAYLOAD}" \
  https://api.github.com/repos/opspresso/argocd-env-demo/dispatches
```

## circle-ci api v2

```bash
PAYLOAD="{\"parameters\":{"
PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
PAYLOAD="${PAYLOAD}\"phase\":\"${TG_PHASE}\","
PAYLOAD="${PAYLOAD}\"type\":\"${TG_TYPE}\""
PAYLOAD="${PAYLOAD}}}"

curl -sL -X POST \
  -u ${PERSONAL_TOKEN}: \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  https://circleci.com/api/v2/project/gh/opspresso/argocd-env-demo/pipeline
```
