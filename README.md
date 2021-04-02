# argocd-env-demo

* <https://github.com/argoproj/argo-cd>

```bash
export TG_USERNAME="nalbam"
export TG_PROJECT="deepracer-timer"
export TG_VERSION="v0.0.0"
export TG_PHASE=""
export TG_TYPE=""

./build.sh
```

## circle-ci api v2

```bash
export TG_USERNAME="nalbam"
export TG_PROJECT="deepracer-timer"
export TG_VERSION="v0.0.0"
export TG_PHASE="demo"
export TG_TYPE="kustomize"

export CIRCLE_API="https://circleci.com/api/v2/project/gh/opspresso/argocd-env-demo/pipeline"

PAYLOAD="{\"parameters\":{"
PAYLOAD="${PAYLOAD}\"TG_USERNAME\":\"${TG_USERNAME}\","
PAYLOAD="${PAYLOAD}\"TG_PROJECT\":\"${TG_PROJECT}\","
PAYLOAD="${PAYLOAD}\"TG_VERSION\":\"${TG_VERSION}\","
PAYLOAD="${PAYLOAD}\"TG_PHASE\":\"${TG_PHASE}\","
PAYLOAD="${PAYLOAD}\"TG_TYPE\":\"${TG_TYPE}\""
PAYLOAD="${PAYLOAD}}}"

curl -X POST \
    -u ${PERSONAL_TOKEN}: \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" "${CIRCLE_API}"
```
