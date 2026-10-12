# Agent Platform 배포

`argocd-env-demo`는 앱·worker와 PostgreSQL·Neo4j·MinIO Helm chart를,
`argocd-env-addons`는 Argo CD·External Secrets·Gateway·관측성을,
`terraform-env-demo`는 AWS 인프라·IAM·EKS Pod Identity·S3를 소유한다.

| 항목 | k3s | EKS |
| --- | --- | --- |
| 용도 | 현재 서비스, c6i.xlarge 단일 노드 | Studio·Memory 서비스 중지, 이전 원본 보존 |
| Phase | `alpha` | `prod` |
| Studio | `studio.opsp.dev` | `studio.opspresso.com`, `agentops.demo.clush.net` |
| Memory | `memory.opsp.dev` | `memory.opspresso.com` |
| PostgreSQL | `agent-studio/postgres`, 5Gi | 같은 서비스, 20Gi gp3 |
| Neo4j | `agent-memory/memory-neo4j`, 5Gi | 같은 서비스, 20Gi 기본 StorageClass(gp3) |
| Object storage | MinIO의 `agent-studio-static`, `agent-memory` | AWS S3 `agent-studio-static` |
| Secret 경로 | `/k8s/k3s-demo/` | `/k8s/eks-demo/` |
| Studio control workers | 활성화, compute resources 미선언 | 활성화, requests/limits 선언 |
| Workspace 실행 Pod | requests·limits 미선언, 볼륨 크기 제한·최대 2개 | CPU·메모리·디스크 한도, 최대 32개·Auto Mode 전용 pool |
| 복구용 legacy Docker PVC | 10Gi local-path 보존, daemon 비활성 | 48Gi gp3 보존, daemon 비활성 |

현재 Studio와 Memory는 alpha에서 서비스한다. EKS의 두 앱은 유지보수 설정으로 웹·worker·ticker를 중지하며 Neo4j도 offline 상태를 유지한다. PostgreSQL·원본 S3·PVC는 삭제하지 않는다. 릴리즈 워크플로는 그대로 유지한다.

k3s의 `*.opsp.dev` 앱은 Traefik Gateway와 cert-manager를 사용한다. EKS의
`*.opspresso.com` 앱은 ALB의 ACM 인증서와 Istio Gateway를 사용한다. Google OAuth 클라이언트에는 사용하는 각 도메인의
`https://<hostname>/api/auth/callback/google` redirect URI를 등록해야 한다.

Studio의 `agent_studio.allowed_hosts`는 정확한 호스트 목록이며, 생략하면 `agent_studio.hostname`만 사용한다.
이 목록으로 `BETTER_AUTH_ALLOWED_HOSTS`와 HTTPRoute의 호스트를 함께 생성한다.
`BETTER_AUTH_URL`은 기본 도메인의 HTTPS origin을 유지하고, 프록시는 원래 `Host`를 전달해야 한다.
추가 도메인의 DNS·TLS 인증서·Gateway 연결은 인프라 저장소에서 구성한다.

`trusted_proxy_cidrs`는 두 앱의 인증 요청에서 신뢰할 프록시 hop 범위를 함께 정한다.
EKS의 ALB·Istio 경로는 VPC CIDR을 사용하고, Traefik 하나를 거치는 k3s는 빈 목록으로
단일 client 주소만 허용한다. 이 값이 없거나 실제 경로와 다르면 여러 사용자가 인증 요청 제한을 공유할 수 있다.

Grafana MCP의 대상은 `grafana_url`로 지정한다. EKS management 클러스터는 내부 Service를,
Grafana가 설치되지 않은 k3s는 같은 Grafana의 HTTPS 주소를 사용한다. 관측 지표의 저장소와
MCP가 접속하는 Grafana API 주소를 구분한다.

## 연결과 권한

PostgreSQL은 pgvector가 포함된 이미지로 `agent_studio`와 `agent_memory` database를
초기화한다. 두 앱은 기존 배포 계약에 따라 `agent_studio` 사용자를 공유한다.
Agent Studio의 DB 전환 중에는 대상 `env/<cluster>.yaml`의 `agent_studio_maintenance: true`를
GitOps에 반영한다. 이 설정은 Studio 앱·오디오/Workspace worker를 0개로 내리고 ticker를
중지하지만 PostgreSQL·Agent Memory는 유지한다. Studio 앱·오디오/Workspace worker Pod가
모두 종료되고 진행 중인 ticker 요청이 끝난 것을 확인한 뒤 백업·복원을 진행한다.
새 DB와 이미지 검증 뒤 `false`로 되돌려 기동한다.
Memory의 웹·queue worker는 `agent_memory_maintenance: true`로 함께 중지한다.
첫 Sync에서 두 앱의 웹·worker·ticker Pod가 종료되고 실행 중 queue 작업이 없는지 확인한다.
그 뒤 별도 Sync에서 `neo4j.offline_maintenance: true`로 Neo4j를 offline 모드로 전환한다.
이 모드는 PVC를 유지하고 DB process를 중지한 채 dump·load 명령을 실행할 수 있게 한다.
복원 후에는 먼저 `neo4j.offline_maintenance: false`로 되돌리고 Neo4j readiness와 데이터를 검증한다.
그 검증이 끝난 뒤 별도 Sync에서 서비스할 환경의 앱·worker·ticker만 재개한다.
`postgres-bootstrap` Sync hook은 두 database에 vector extension을 활성화한다.
Studio와 Memory는 자기 이미지가 제공하는 시작 절차로 빈 DB를 초기화한다.
Memory의 기존 schema fingerprint가 다르면 시작을 거부하며 자동으로 데이터를 초기화하지 않는다.

Neo4j는 공식 Helm chart의 Community 단일 인스턴스다. 앱은 내부 Bolt 서비스만 사용한다.
PostgreSQL·Neo4j는 두 환경 모두 단일 인스턴스이며, EKS 리소스 설정이 DB 고가용성이나
백업을 제공하는 것은 아니다. 별도 백업·복구 운영이 필요하다.

EKS에서 S3 SDK는 service account에 연결된 Pod Identity를 사용한다. MinIO endpoint와
정적 S3 credential은 EKS에 주입하지 않는다. `agent-memory` 이미지에는 기본 AWS
credential chain을 허용하는 S3 설정 코드가 포함되어 있어야 한다.

| IAM role | 서비스 계정 | S3 객체 범위 |
| --- | --- | --- |
| `pod-role--agent-studio` | `agent-studio/agent-studio` | `artifacts/*`, `images/*`, `source-files/*` |
| `pod-role--agent-memory` | `agent-memory/agent-memory` | `organizations/*/documents/*` |

버킷은 비공개로 설정하고 TLS 접근만 허용한다. Studio는 `ARTIFACT_ACCESS_MODE=proxied`로
접근 권한을 검사하고 Memory는 인증된 문서 API를 사용한다. Studio IAM policy에는
DynamoDB·Bedrock·S3 Vectors 권한을 두지 않는다. k3s는 MinIO를 사용하므로 노드에
Studio S3 policy를 연결하지 않는다.

앱 namespace의 기존 ECR 인증 리소스는 유지한다. 실행 전용 namespace에는 External Secrets의
`ECRAuthorizationToken` generator로 imagePullSecret을 공급한다. EKS는 controller의 Pod Identity,
k3s는 기존 EC2 역할로 인증한다. Workspace image는 Studio와 함께 발행된 tag를 사용한다.
`agent-studio-workspace` ConfigMap은 최종 `app.image.repository`와 phase의 `app.image.tag`로
`WORKSPACE_IMAGE=<repository>:workspace-<tag>`를 만들며 앱과 worker가 함께 읽는다.
같은 ConfigMap의 `WORKSPACE_MODEL_GATEWAY_URL`은 최종 Studio Service 이름·namespace·서비스
포트로 구성한다. Native CLI는 이 주소의 인증된 모델 Gateway를 호출하며 공급자 키를 받지 않는다.
환경 파일에 Workspace 버전을 따로 고정하지 않는다. 전환·PVC 보존·drain gate는
[Kubernetes Workspace 운영](workspace-kubernetes.md)을 따른다.

EKS의 embedding과 knowledge extraction은 공개 provider를 사용한다. k3s에서 접근하는
`100.66.249.76`의 self-hosted endpoint를 EKS에서 접근 가능하다고 가정하지 않는다.
기존 DB의 Settings override는 환경변수보다 우선하므로 provider 변경 시 함께 확인한다.

## 코딩·오디오 실행 준비

production의 동시성·DB 연결·노드 용량은 [용량 운영](production-capacity.md)을 따른다.

두 환경의 Workspace는 `agent-studio-workspaces` namespace의 Pod로 실행한다. 기본 거부
NetworkPolicy, 명시적 DNS·egress, 최소 RBAC와 ResourceQuota를 함께 적용한다. 내부 모델 endpoint를
호출하는 Studio만 공급자 연결을 사용한다. Sandbox에는 해당 Studio 앱 Pod·컨테이너 포트만
추가 허용하며 같은 namespace의 다른 서비스나 Kubernetes API를 허용하지 않는다.
그 밖의 내부 endpoint가 필요한 설치는 정확한 목적지와 포트를 추가한다. 실제 격리는 테스트 Pod의 요청으로 확인한다.

EKS의 NetworkPolicy는 addons의 `eks-network-policy-eks-demo` controller에 의존한다.
Auto Mode의 전용 NodeClass는 DefaultDeny를 사용하며, k3s는 기본 network policy controller를 유지한다.

`workspace_legacy_docker=true`로 복구하는 동안 `agent-studio-public` Docker bridge와
`tcp-docker` Service를 사용한다. `python3 scripts/check_agent_network.py --context eks-demo`는
legacy 경로를 검사하고, Docker Pod·Service가 없는 현재 구성에서는 `SKIP`을 보고한다.
새 실행 Pod의 RBAC·DNS·통신 차단·quota·복원은 Agent Studio의 Kubernetes 통합 검사와
승인 후 클러스터 검증으로 확인한다.

Workspace Git 작업은 해당 Agent에 연결된 GitHub MCP의 호출자 개인 OAuth 권한을 사용한다.
Sandbox에 GitHub token을 넘기지 않는다. 프로젝트의 저장소 정책, 기본 Runtime, Models의 Runtime별
모델 선택과 배포 workflow 허용 목록은 Studio에서 관리한다. GitHub MCP 연결만으로 이 준비가 끝나지는 않는다.

worker liveness는 `workspace-heartbeat-check.cjs`로 실제 heartbeat 만료를 확인한다.
이 실행파일을 포함하는 Studio 이미지를 먼저 릴리스·배포한 뒤 변경한 chart를 동기화한다.
readiness는 `--worker` 모드로 선택한 Sandbox 백엔드·모델 설정을 확인한다. 30초마다 검사하고
실패 1회로 readiness를 내리므로 명목 실패 감지 시간은 30초다. liveness는 외부 의존성을 호출하지 않는다.

scan·plugin sync·reindex는 하나의 `agent-studio-ticker` Deployment가 호출한다. scan과 plugin sync는
요청 시간을 포함해 매분, reindex는 시작 시와 매시간 실행한다. HTTP 실패는 각각 기록하고 다음 정기
호출을 기다린다. 유지보수 설정은 ticker도 0개로 내린다. 매분 Job Pod를 생성하지 않는다.

오디오에는 등록된 transcription 모델, Plaud OAuth, 프로젝트 AudioJob config, 비공개 저장소와
audio-worker가 모두 필요하다. 테스트·운영의 설정과 연결은 각각 확인한다. 모델이 없어진 config를
그대로 재사용하지 않는다. `agent-plugins`의 [Audio 프로필](https://github.com/opspresso/agent-plugins/blob/main/docs/audio-agent.md)과
[Workspace 프로필](https://github.com/opspresso/agent-plugins/blob/main/docs/code-agent.md)을 따른다.

로컬 Docker에서 실제 방화벽 동작을 확인한다. 이 검사는 별도 DinD에서 공개 HTTPS와 정상 동작하는
내부 HTTP fixture를 사용하며, 자신의 컨테이너·볼륨만 정리한다.

```bash
python3 scripts/check_workspace_network.py
```

## 최초 배포 순서

1. 앱 릴리스의 검증·image 게시를 확인한다. Memory 이미지는 `build/worker.cjs`,
   Studio 이미지는 같은 tag의 Workspace 이미지를 함께 제공해야 한다.
2. `terraform-env-demo/demo/4-role`, `demo/5-eks`, `demo/8-agent-studio`에서
   S3·ECR·Pod Identity·k3s 인프라와 DNS/TLS 연결을 준비한다. 변경 전 plan을 검토하고
   기존 EC2·volume·bucket을 보존한다. k3s의 cert-manager에는 `opsp.dev` DNS-01 권한이 필요하다.
3. EKS의 연결 Secret을 확인하고, 승인된 최초 설치에서 없을 때만 생성한다.

   ```bash
   python3 scripts/bootstrap_agent_platform.py --cluster eks-demo
   python3 scripts/bootstrap_agent_platform.py --cluster eks-demo --apply
   ```

   생성 대상은 PostgreSQL·Neo4j 연결과 Memory metrics token이다. 값은 SecureString으로
   전달하고 로그에 출력하지 않는다. 기존 값은 덮어쓰지 않으며 서로 맞지 않는 부분 설정은 거부한다.
   OAuth·provider·암호화·scan token은 각 chart의 ExternalSecret 참조를 확인한다.
4. App of Apps를 등록하고 PostgreSQL·Neo4j, k3s의 MinIO를 준비한다.
   Secret 동기화, 기존 PVC의 보존, DB readiness를 확인한 뒤 앱을 배포한다.
5. phase의 image tag와 생성 values를 GitOps로 반영한다. 웹·worker가 모두 Ready이고
   Argo CD가 `Synced/Healthy`인지 확인한다. Memory의 웹만 실행하면 queue는 소비되지 않는다.
6. 공개 호스트의 DNS·TLS·인증, 앱 readiness·metrics, worker 처리와 MCP의 하류 API 호출을
   확인한다. 필요한 Workspace 검사는 [Kubernetes Workspace 운영](workspace-kubernetes.md)을 따른다.

## 검증

```bash
GITHUB_PUSH=false bash scripts/build.sh
python3 scripts/validate.py --all-charts
pytest
```

Memory 웹의 readiness `/api/health`는 PostgreSQL·schema·Neo4j를 제한된 시간 안에 검사한다.
Startup·liveness `/api/live`는 의존 서비스와 분리해 HTTP event loop의 응답을 확인한다.
Memory HPA는 웹 CPU를, Studio HPA는 `agent_studio_active_execution_requests`와 앱 CPU를 사용한다.
Memory worker는 별도 replica·종료 유예를 사용하며 startup 이후 probe HTTP를 제공한다.
Memory 웹·worker metrics는 같은 전용 `METRICS_BEARER_TOKEN`으로 인증한다.

배포 후에는 Argo CD health와 함께 각 앱의 DB readiness, S3/MinIO 쓰기·읽기·정리,
Memory 문서 처리, Studio audio·workspace worker, OAuth 로그인, Prometheus scrape를 확인한다.
Health 응답만으로 object storage·provider·worker 처리 성공을 판정하지 않는다.

### PostgreSQL 이미지와 정렬 규칙

PostgreSQL 이미지의 OS·libc가 바뀌면 기존 DB의 정렬 규칙 버전도 확인한다. 접속 가능한
DB에서 다음 조회를 실행하고 앱 DB뿐 아니라 새 DB의 원본인 `template1`도 대조한다.

```sql
SELECT datname, datcollversion,
       pg_database_collation_actual_version(oid) AS actual_version
FROM pg_database;
```

버전이 다르면 해당 DB에 연결해 의존하는 인덱스·저장 객체를 확인하고 먼저 재구성한다.
그 뒤에 `ALTER DATABASE ... REFRESH COLLATION VERSION`을 실행한다. 명명된 collation도
현재 DB의 encoding에 적용 가능한 항목을 확인한다. 빈 기본 DB에서 버전 정보만 갱신하려면
사용자 객체와 해당 collation에 의존하는 객체가 없음을 먼저 증명해야 한다.
앱 DB·보관 DB를 일괄 초기화하거나 경고를 없애기 위해 버전만 덮어쓰지 않는다.
[PostgreSQL의 collation 복구 절차](https://www.postgresql.org/docs/18/sql-altercollation.html#SQL-ALTERCOLLATION-NOTES)를 따른다.
