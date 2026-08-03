# argocd-env-demo

## apps

> apps 를 등록 합니다.

```bash
kubectl apply -n argocd -f https://raw.githubusercontent.com/opspresso/argocd-env-demo/main/apps.yaml
```

## charts

```
charts/<project>/
  Chart.yaml
  values.yaml                  # 공통 값
  values-<phase>.yaml          # phase 별 값. 배포시 gitops 가 갱신
  versions-<phase>.json        # phase 별 배포 이력
  values-template.yaml.j2      # jinja2 템플릿 (phase 아님)
  <env>/values-<cluster>.yaml  # build.sh 가 env/*.yaml 로 렌더한 결과
```

`phase` 는 `values-<phase>.yaml` 파일에서 찾는다. `values-template.yaml.j2` 는 렌더 소스이므로
phase 로 취급하지 않는다.

`<env>/values-<cluster>.yaml` 은 **언제나** `values-template.yaml.j2` 의 렌더 결과다.
직접 고치지 말고 템플릿을 고친 뒤 `./build.sh` 를 돌린다.
덮어쓸 값이 없는 chart 도 템플릿을 둔다 — ApplicationSet 의 `valueFiles` 에 적힌 파일이 없으면
sync 에 실패하기 때문이다.

ApplicationSet 은 `env/*.yaml` 의 `phase` 필드로 어떤 `values-<phase>.yaml` 을 읽을지 정한다.
현재 env 파일은 모두 `phase: alpha` 라 `values-prod.yaml` 을 읽는 클러스터는 없다.

## gitops

* <https://github.com/argoproj/argo-cd>

`repository_dispatch` → [`.github/workflows/gitops.yml`](.github/workflows/gitops.yml) →
`gitops.sh` → `gitops.py`

| client_payload | 설명 |
|---|---|
| `username` | 이미지 owner |
| `project` | 차트 이름 (`charts/<project>`) |
| `version` | 배포할 버전 |
| `container` | 갱신할 values 최상위 키. 기본 `app` |
| `action` | 비움 또는 `approved` |
| `phase` | 대상 phase. **비우면 차트의 모든 phase 로 fan-out** |
| `type` | `helm` |

`prod` 는 브랜치를 만들어 PR 을 올리고, 나머지 phase 는 `main` 에 바로 푸시한다.

```bash
PAYLOAD="{\"event_type\":\"gitops\","
PAYLOAD="${PAYLOAD}\"client_payload\":{"
PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
PAYLOAD="${PAYLOAD}\"phase\":\"${TG_PHASE}\","
PAYLOAD="${PAYLOAD}\"type\":\"helm\""
PAYLOAD="${PAYLOAD}}}"

curl -sL -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer ${GITHUB_TOKEN}" \
  -d "${PAYLOAD}" \
  https://api.github.com/repos/opspresso/argocd-env-demo/dispatches
```

### 로컬 실행

`--dry-run` 은 파일만 갱신하고 git·GitHub 은 건드리지 않는다.

```bash
export TG_PROJECT="sample-grpc"
export TG_VERSION="v0.0.0"
export TG_PHASE="alpha"

python3 gitops.py deploy --dry-run
```

`TG_PHASE` 를 비우면 phase 목록을 찾아 fan-out 한다.

```bash
TG_PROJECT="sample-grpc" TG_VERSION="v0.0.0" python3 gitops.py dispatch --dry-run
```

## build

`values-template.yaml.j2` 를 `env/*.yaml` 마다 렌더해 `charts/<project>/<env>/` 에 저장한다.

```bash
./build.sh
```

## validate

ApplicationSet 이 지정한 것과 같은 valueFiles 조합으로 `helm template` 을 돌린다.
values 파일 누락이나 chart 오류를 Argo CD sync 가 아니라 CI 에서 잡기 위한 것이다.

```bash
./validate.py

./validate.py -r sample-node
```

## test

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest
```
