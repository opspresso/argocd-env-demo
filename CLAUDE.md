# CLAUDE.md

애플리케이션을 Argo CD 로 배포하는 GitOps 저장소.

> 클러스터 addon 배포는 `argocd-env-addons` 저장소가 담당한다.
> 두 저장소는 디렉토리 모양이 닮았지만 **chart 규칙이 다르다** — 마지막 절 참고.

## 저장소 구조

```
apps.yaml              # App of Apps. Application `apps-demo` 가 apps/ 를 sync
apps/<project>.yaml    # application 별 ApplicationSet (배포 대상)
charts/<project>/      # wrapper Helm chart
env/<cluster>.yaml     # 클러스터별 변수. git files generator 입력이자 Jinja2 렌더 입력
gen_values.py          # values-template.yaml.j2 × env/*.yaml → charts/<project>/<env>/values-<cluster>.yaml
build.sh               # 모든 chart 에 gen_values.py 실행. CI 에서 결과를 자동 커밋
gitops.py              # repository_dispatch 로 들어온 버전을 values-<phase>.yaml 에 기록
gitops.sh              # gitops.py 래퍼 (workflow 호출 규약 유지용)
chart.py               # chart 파일 조작 — phase 탐색, values/versions 갱신
validate.py            # ApplicationSet 과 같은 조합으로 helm template 검증
tests/                 # pytest
```

## charts 규칙

```
charts/<project>/
  Chart.yaml                    # wrapper chart. upstream chart 를 dependency 로 고정
  values.yaml                   # 모든 phase·클러스터 공통 값
  values-<phase>.yaml           # phase 별 값. 배포 시 gitops 가 버전을 갱신
  versions-<phase>.json         # phase 별 배포 이력
  values-template.yaml.j2       # Jinja2 템플릿 (렌더 소스, phase 아님)
  <env>/values-<cluster>.yaml   # build.sh 가 env/*.yaml 로 렌더한 결과
```

### 파일별 편집 규칙

| 파일 | 직접 수정 |
|---|---|
| `Chart.yaml` | O |
| `values.yaml` | O |
| `values-<phase>.yaml` | O — 단, 버전 관련 키는 gitops 소유(아래) |
| `versions-<phase>.json` | **X** — gitops 산출물 |
| `values-template.yaml.j2` | O |
| `<env>/values-<cluster>.yaml` | **X** — 언제나 생성물 |

**`<env>/values-<cluster>.yaml` 은 예외 없이 `values-template.yaml.j2` 의 렌더 결과다.**
클러스터별 값을 바꾸려면 템플릿을 고치고 `./build.sh` 를 돌린다. 렌더 결과를 직접 고치면
다음 build 에서 덮어써진다. `validate.py` 가 이 규칙을 검사하므로, 템플릿 없이 env 디렉토리만
있는 chart 는 CI 에서 실패한다.

클러스터별로 덮어쓸 값이 없는 chart 도 템플릿을 둔다. ApplicationSet 의 `valueFiles` 에 적힌
파일이 없으면 Argo CD 가 sync 에 실패하기 때문이다.

`values-<phase>.yaml` 은 배포마다 `yaml.safe_dump` 로 통째로 재작성된다 (`chart.py:135`).
**주석은 사라지고 키는 알파벳 순으로 재정렬된다** — 설명이 필요하면 `values.yaml` 이나
템플릿에 적는다.

이 파일에서 `gitops.py` 가 소유하는 키는 손대지 않는다 — `container` 키(기본 `app`) 아래의
`image.tag`, `configmap.data.VERSION`, `secret.data.SECRET_VERSION`,
`env[]` 의 `VERSION`·`ENV_HASH`.

`ENV_HASH` 는 **`values-<phase>.yaml` 만** 해시한 값이다 (`chart.py:157`). `values.yaml` 이나
`<env>/values-<cluster>.yaml` 이 바뀌어도 움직이지 않는다. 다만 pod 재시작은 이것에 의존하지
않는다 — upstream `app` chart 가 `checksum/config`·`checksum/secret` 을 병합된 값 전체에서
계산해 deployment 에 달아준다. `ENV_HASH` 는 앱이 자기 버전을 env 로 읽기 위한 값에 가깝다.

`ENV_HASH` 는 배포할 때만 다시 계산된다. 그래서 `values-<phase>.yaml` 을 손으로 고치면 다음 배포
전까지 옛 해시가 남고, **같은 버전을 다시 배포해도 `ENV_HASH` 한 줄은 바뀐다.** 재배포 diff 에
이 줄만 있으면 정상이다.

### phase

- phase 는 `values-<phase>.yaml` 파일 존재로 결정된다 (`chart.discover_phases`).
- 템플릿이 `values-template.yaml.j2` 인 이유가 이것이다 — `.yaml` 이면 phase 패턴에 걸린다.
  `template` 은 `chart.RESERVED_PHASES` 에 남겨 둔 안전장치다. 옛 이름을 쓰는 chart 가 남아도
  phase 로 잡히지 않는다. 이 예외가 없던 시절 `versions-template.json` 이 생겼던 적이 있다.
- 새 phase 를 추가하려면 `values-<phase>.yaml` 을 만들면 된다. `versions-<phase>.json` 은
  첫 배포 때 자동 생성된다.
- `prod` 만 특별하다 — 브랜치를 만들어 PR 을 올린다. 나머지는 `main` 에 바로 push.
- **`prod` 는 아직 소비처가 없다.** `env/*.yaml` 세 개가 모두 `phase: alpha` 라
  `values-prod.yaml` 을 읽는 클러스터가 없다. `TG_PHASE` 없이 dispatch 하면 prod 도 fan-out 되어
  PR 이 만들어지고 mergify 가 머지하지만, 그 값은 어느 클러스터에도 반영되지 않는다.
  prod 클러스터를 붙일 때 `env/<cluster>.yaml` 에 `phase: prod` 를 넣으면 그때부터 연결된다.

### Chart.yaml

- 자체 SemVer 를 쓴다 (`v1.3.0`). upstream chart 버전을 그대로 쓰는 addons 저장소와 다르다.
- 애플리케이션 chart 는 `opspresso/helm-charts` 의 `app` chart 를 dependency 로 쓴다.
  `app` chart 버전을 올릴 때 wrapper `version` 도 함께 올린다.
- 한 chart 를 두 번 쓰거나 이름을 바꿔 붙일 때는 `alias` 로 values 키를 정한다
  (예: agentdure 의 `cronjob` → `scan`).

### values 병합 순서

ApplicationSet 의 `helm.valueFiles` 순서 그대로다. 뒤가 앞을 덮는다.

1. `values.yaml`
2. `values-<phase>.yaml`
3. `<env>/values-<cluster>.yaml`

`phase` 는 `env/<cluster>.yaml` 의 `phase` 필드에서 온다. 즉 **클러스터가 phase 를 고른다.**

## env/<cluster>.yaml

- 파일 이름이 클러스터 이름이고, 안의 `cluster` 필드와 일치해야 한다 (`{{cluster}}` 로 치환됨).
- `env` 는 렌더 출력 디렉토리이자 valueFiles 경로가 된다 (`{{env}}/values-{{cluster}}.yaml`).
  `gen_values.py` 는 `env` 가 없으면 실패한다.
- `phase` 는 그 클러스터가 읽을 `values-<phase>.yaml` 을 정한다.
- env 파일을 추가하면 `build.sh` 가 모든 chart 에 대해 렌더 결과를 새로 만든다.

## apps/<project>.yaml

- `kind: ApplicationSet` + git files generator 로 `env/*.yaml` 을 읽어 클러스터별로 fan-out 한다.
- 배포할 클러스터는 `generators.git.files` 의 주석을 풀어 고른다.
- Application 이름은 `<project>-{{cluster}}`.
- label `opspresso.com/group: apps`, `opspresso.com/cluster: {{cluster}}` 를 유지한다.
- `syncPolicy.automated` 는 chart 마다 다르다. 켜져 있는 것을 임의로 끄거나 반대로 켜지 않는다.
- `apps/` 에 ApplicationSet 이 없는 chart 는 배포되지 않는다 (`charts/sample-spring`).

## gitops

`repository_dispatch` → `.github/workflows/gitops.yml` → `gitops.sh` → `gitops.py`.
payload 필드와 curl 예시는 [README](README.md#gitops) 참고.

- `TG_PHASE` 가 있으면 그 phase 를 배포(`deploy`), 없으면 chart 의 모든 phase 로 fan-out(`dispatch`).
- 배포는 `values-<phase>.yaml` + `versions-<phase>.json` 을 갱신하고 `nalbam-bot` 으로 커밋한다.
- 같은 버전을 다시 배포하면 파일이 바뀌지 않아 커밋 없이 끝난다 (idempotent).
- 워크플로는 `concurrency: gitops` 로 직렬화된다. 취소하면 chart 가 절반만 쓰인 채 남는다.
- 로컬 확인은 `--dry-run` 으로 한다. 파일만 갱신하고 git·GitHub 은 건드리지 않는다.

```bash
TG_PROJECT="sample-grpc" TG_VERSION="v0.0.0" TG_PHASE="alpha" python3 gitops.py deploy --dry-run
```

## 재생성 · 검증

```bash
./build.sh                       # 전체 chart 렌더
./gen_values.py -r mcp-memory    # 한 chart 렌더
./validate.py                    # helm template 로 전체 검증
./validate.py -r sample-node     # 한 chart 만
pytest                           # chart.py / gitops.py 테스트
```

`.github/workflows/validate.yml` 이 PR 과 main push 에서 `build.sh` → `validate.py` 를 돌린다.
렌더한 뒤 검증하므로 PR 에 렌더 결과가 빠져 있어도 템플릿 변경분이 검사된다.
`apps/` 에 ApplicationSet 이 없는 chart(`sample-spring`)는 배포되지 않으므로 검증 대상도 아니다.

`validate.py` 는 `helm dependency update` 로 upstream chart 를 내려받는다.
결과물(`charts/*/charts/`, `charts/*/Chart.lock`)은 `.gitignore` 처리되어 있다.

`main` 에 push 하면 `.github/workflows/push.yml` 이 `build.sh` 를 돌려 렌더 결과를
`nalbam-bot` 이름으로 자동 커밋한다. `gitops.py` / `chart.py` 를 고치면 `tests/` 도 함께 본다.

## argocd-env-addons 와 다른 점

같은 이름의 파일이 다른 의미를 가지므로 두 저장소를 오갈 때 주의한다.

| | argocd-env-demo (여기) | argocd-env-addons |
|---|---|---|
| 배포 단위 | application | addon |
| 템플릿 파일 | `values-template.yaml.j2` | 같음 |
| phase | `values-<phase>.yaml`, `versions-<phase>.json` | 없음 |
| `env/*.yaml` | `phase` 필드 있음 | `phase` 필드 없음 |
| valueFiles | `values.yaml` → `values-<phase>.yaml` → `<env>/values-<cluster>.yaml` | `values-<phase>.yaml` 단계가 없음 |
| 렌더 출력 경로 | `charts/<project>/<env>/` | 같음 |
| chart 버전 | 자체 SemVer | upstream chart 버전을 그대로 |
| 버전 배포 | `repository_dispatch` → `gitops.py` | 없음 (수동 chart 버전 변경) |

## 관련 저장소

- `argocd-env-addons` — 클러스터 addon 배포. Argo CD·Istio·external-secrets 등 이 저장소의 전제.
- `terraform-env-demo` — EKS·VPC·ALB·IAM Role.
- `opspresso/helm-charts` — dependency 로 쓰는 `app`, `cronjob` chart 의 저장소.
