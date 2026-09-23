# argocd-env-demo

Agent Studio·Memory의 k3s/EKS 구성, 저장소별 책임, Secret 준비와 배포 순서는
[Agent Platform 배포](docs/agent-platform.md)를 따른다.

## 저장소 구조

```text
apps-*.yaml       # App of Apps 설치 진입점
apps/             # 플랫폼별 Argo CD Application/ApplicationSet
charts/           # Helm chart와 배포 버전
env/              # 클러스터별 설정
scripts/          # 빌드·GitOps·검증·운영 스크립트
requirements/     # Python 실행(runtime.txt)·테스트(dev.txt) 의존성
tests/            # 자동화 테스트
docs/             # 운영 문서
```

아래 명령은 저장소 루트 기준이다. 스크립트는 다른 디렉터리에서도 경로를 지정해 실행할 수 있다.

## apps

> apps 를 등록 합니다.

```bash
kubectl apply -n argocd -f https://raw.githubusercontent.com/opspresso/argocd-env-demo/main/apps-eks.yaml
kubectl apply -n argocd -f https://raw.githubusercontent.com/opspresso/argocd-env-demo/main/apps-k3s.yaml
```

ApplicationSet은 `apps/eks/`와 `apps/k3s/`로 분리한다. 각 디렉터리는 해당 플랫폼의
클러스터만 읽는다.

replica 수, autoscaling 여부와 resource 사용 여부는 `env/<cluster>.yaml`이 원천이다.
공통 `values.yaml`은 EKS를 기본으로 하며 EKS는 기존 env 설정을 적용한다.
k3s·local 환경은 `replicas: 1`, `autoscaling: false`, `resources: false`로 선언한다.
metrics backend는 `metrics.backend`로 선택하며, k3s는 `victoria-metrics`, EKS는
`prometheus`를 사용한다.
각 chart의 기본 values가 운영용 requests/limits를 제공하며, `resources: false`인
환경에서는 템플릿이 해당 resource block을 제거한다. 컨테이너·초기화 컨테이너·worker·CronJob에도 같은 규칙을 적용한다.
HPA·VPA·KEDA autoscaler를 생성하지 않으며 PVC storage 요청은 유지한다.
`scripts/validate.py`는 k3s·local 렌더 결과에 compute requests/limits나 autoscaler가 남으면 실패한다.

## 로컬 Kubernetes 개발 환경

실행 제품은 OrbStack 또는 Docker Desktop이며 배포 환경 이름은 `local`로 통일한다.
`argocd` namespace와 Helm release를 사용하고, Mac 연결은 addons의
`install/local/connect.py`로 localhost 포워딩을 유지한다.

`apps-local.yaml`은 `apps/local/`를 동기화한다. `env/local-demo.yaml`과 기존 chart의
`values-template.yaml.j2`에서 `local/values-local-demo.yaml`을 생성한다. PostgreSQL·MinIO·
Neo4j·MCP 5종을 배포하며, Studio·Memory는 Mac에서 `pnpm`으로 실행한다.
namespace·서비스 주소·SSM·External Secrets는 기존 k3s 규칙을 따른다.
local은 `resources: false`로 모든 컨테이너의 CPU·메모리 requests/limits를 선언하지 않는다.
Argo CD bootstrap은 형제 `argocd-env-addons/install/local/`를 사용한다.

```bash
GITHUB_PUSH=false bash scripts/build.sh
python3 scripts/validate.py -d apps/local
```

## charts

```
charts/<project>/
  Chart.yaml
  values.yaml                  # 공통 값
  values-<phase>.yaml          # phase 별 값. 배포시 gitops 가 갱신
  versions-<phase>.json        # phase 별 배포 이력
  values-template.yaml.j2      # jinja2 템플릿 (phase 아님)
  <platform>/values-<cluster>.yaml # scripts/build.sh 가 해당 플랫폼 env로 렌더한 결과
```

`phase` 는 `values-<phase>.yaml` 파일에서 찾는다. `values-template.yaml.j2` 는 렌더 소스이므로
phase 로 취급하지 않는다.

`<platform>/values-<cluster>.yaml` 은 **언제나** `values-template.yaml.j2` 의 렌더 결과다.
직접 고치지 말고 템플릿을 고친 뒤 `./scripts/build.sh` 를 돌린다.
덮어쓸 값이 없는 chart 도 템플릿을 둔다 — ApplicationSet 의 `valueFiles` 에 적힌 파일이 없으면
sync 에 실패하기 때문이다.

ApplicationSet 은 `env/*.yaml` 의 `phase` 필드로 어떤 `values-<phase>.yaml` 을 읽을지 정한다.
`k3s-demo`는 `phase: alpha`, `eks-demo`는 `phase: prod`를 사용한다.
앱과 MCP의 두 phase values를 별도로 관리한다.

클러스터별 SSM 경로는 `values-template.yaml.j2`가 `env/<cluster>.yaml`의 `cluster`에서
생성한다. 공통 `values.yaml`에는 특정 클러스터의 `ssmPrefix`를 두지 않는다.
PostgreSQL·MinIO·Neo4j는 클러스터 values가 없으면 렌더링에 실패하며, `scripts/validate.py`는
최종 `ssmPrefix`가 대상 클러스터와 다르면 실패한다. EKS 공통 기본값과 클러스터의
자격 증명 경로는 별개다.

## gitops

* <https://github.com/argoproj/argo-cd>

`repository_dispatch` → [`.github/workflows/gitops.yml`](.github/workflows/gitops.yml) →
`scripts/gitops.sh` → `scripts/gitops.py`

| client_payload | 설명 |
|---|---|
| `username` | 이미지 owner |
| `project` | 차트 이름 (`charts/<project>`) |
| `version` | 배포할 버전 |
| `container` | 갱신할 values 최상위 키. 기본 `app` |
| `action` | 비움 또는 `approved`. 승인 이력 기록용이며 머지 방식과는 독립적 |
| `phase` | 대상 phase. **비우면 차트의 모든 phase 로 fan-out** |
| `type` | `helm` |
| `auto_merge` | JSON boolean. 기본 `false`; `true`면 prod도 `main`에 즉시 반영 |

`alpha` 등 prod 이외의 phase는 `main`에 바로 푸시한다. `prod`는 기본적으로
브랜치를 만들어 PR을 올리며, `auto_merge: true`를 지정하면 PR 생성 없이
`main`에 바로 푸시한다. GitHub의 브랜치 보호 규칙은 그대로 적용된다.
`phase`를 비워 fan-out 할 때도 `auto_merge`가 각 이벤트에 전달되므로 prod에 적용된다.

예를 들어 prod를 즉시 반영하는 payload는 다음과 같다.

```json
{
  "event_type": "gitops",
  "client_payload": {
    "project": "sample-node",
    "version": "v1.2.3",
    "phase": "prod",
    "auto_merge": true
  }
}
```

```bash
PAYLOAD="{\"event_type\":\"gitops\","
PAYLOAD="${PAYLOAD}\"client_payload\":{"
PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
PAYLOAD="${PAYLOAD}\"phase\":\"${TG_PHASE}\","
PAYLOAD="${PAYLOAD}\"auto_merge\":${TG_AUTO_MERGE:-false},"
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
실제 배포는 미커밋 변경·미추적 파일·미푸시 커밋이 없는 `main` checkout에서 실행한다.
배포 커밋에는 대상 `values-<phase>.yaml`과 `versions-<phase>.json`만 포함한다.

```bash
export TG_PROJECT="sample-grpc"
export TG_VERSION="v0.0.0"
export TG_PHASE="alpha"

python3 scripts/gitops.py deploy --dry-run
```

prod 즉시 반영은 `TG_AUTO_MERGE=true` 또는 `--auto-merge`로 선택한다.
환경변수는 `true`·`false`만 허용하며(대소문자 무관), 비우면 `false`다.
`--auto-merge`는 환경변수의 `false`보다 우선한다.

```bash
TG_PROJECT="sample-node" TG_VERSION="v1.2.3" TG_PHASE="prod" \
  python3 scripts/gitops.py deploy --auto-merge --dry-run
```

실제로 반영하려면 `--dry-run`을 제외한다. 같은 버전의 prod 브랜치가 이미 있으면
기존 PR은 중복 생성하거나 다시 열지 않고, 브랜치만 있고 PR 생성이 실패했던 경우는
PR 생성을 재개한다. `auto_merge`는 기존 PR 유무와 관계없이 `main`을 갱신하며,
기존 PR을 닫거나 머지하지는 않는다.

`TG_PHASE` 를 비우면 phase 목록을 찾아 fan-out 한다.

```bash
TG_PROJECT="sample-grpc" TG_VERSION="v0.0.0" python3 scripts/gitops.py dispatch --dry-run
```

## build

`values-template.yaml.j2` 를 플랫폼에 맞는 `env/*.yaml` 마다 렌더해
`charts/<project>/<platform>/` 에 저장한다.

```bash
./scripts/build.sh
```

## validate

ApplicationSet 이 지정한 것과 같은 valueFiles 조합으로 `helm template` 을 돌린다.
values 파일 누락이나 chart 오류를 Argo CD sync 가 아니라 CI 에서 잡기 위한 것이다.

```bash
./scripts/validate.py

./scripts/validate.py -r sample-node
```

## k3s workers

k3s의 `agent-studio`는 `audio-worker`를 별도 Deployment로 실행한다. Workspace 기능은
`workspace-worker`와 Docker-in-Docker sidecar를 사용하며, sandbox Docker daemon은
`agent-studio-workspace-docker` ClusterIP로 앱과 worker만 접근한다. Docker state는
`agent-studio-workspace-docker` PVC에 보존하고, sandbox image는 private ECR의
`agent-studio:workspace-<version>` tag를 사용한다.

Workspace worker Pod는 DinD 때문에 privileged 권한이 필요하다. `ecr-registry` Secret은
kubelet image pull뿐 아니라 worker와 앱의 Docker client config에도 mount해야 하며,
Agent Studio image와 matching Workspace image를 함께 release해야 한다.

## test

```bash
pip install -r requirements/runtime.txt -r requirements/dev.txt
pytest
```
