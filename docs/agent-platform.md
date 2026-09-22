# Agent Platform 배포

`argocd-env-demo`는 앱·worker와 PostgreSQL·Neo4j·MinIO Helm chart를,
`argocd-env-addons`는 Argo CD·External Secrets·Gateway·관측성을,
`terraform-env-demo`는 AWS 인프라·IAM·EKS Pod Identity·S3를 소유한다.

| 항목 | k3s | EKS |
| --- | --- | --- |
| 용도 | c6i.xlarge 단일 노드 테스트 | requests/limits·HPA·PDB를 적용하는 환경 |
| Phase | `alpha` | `prod` |
| Studio | `studio.opsp.dev` | `studio.opspresso.com` |
| Memory | `memory.opsp.dev` | `memory.opspresso.com` |
| PostgreSQL | `agent-studio/postgres`, 5Gi | 같은 서비스, 20Gi gp3 |
| Neo4j | `agent-memory/memory-neo4j`, 5Gi | 같은 서비스, 20Gi 기본 StorageClass(gp3) |
| Object storage | MinIO의 `agent-studio-static`, `agent-memory` | AWS S3 `agent-studio-static` |
| Secret 경로 | `/k8s/k3s-demo/` | `/k8s/eks-demo/` |
| Studio audio·workspace | 활성화, compute resources 미선언 | 활성화, requests/limits 선언 |
| Workspace Docker PVC | 10Gi local-path | 20Gi gp3 |

k3s의 `*.opsp.dev` 앱은 Traefik Gateway와 cert-manager를 사용한다. EKS의
`*.opspresso.com` 앱은 ALB의 ACM 인증서와 Istio Gateway를 사용한다. Google OAuth 클라이언트에는 사용하는 각 도메인의
`https://<hostname>/api/auth/callback/google` redirect URI를 등록해야 한다.

## 연결과 권한

PostgreSQL은 pgvector가 포함된 이미지로 `agent_studio`와 `agent_memory` database를
초기화한다. 두 앱은 기존 배포 계약에 따라 `agent_studio` 사용자를 공유한다.
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

EKS의 workspace Docker client credential은 External Secrets의 `ECRAuthorizationToken`
generator로 매시간 갱신한다. AWS 접근은 External Secrets controller의 Pod Identity가
담당한다. k3s의 `ecr-registry`는 기존 노드 갱신 절차가 소유한다. Workspace image는
Studio와 함께 발행된 tag를 사용하며, workspace worker는 단일 PVC 때문에 `Recreate`로 배포한다.

EKS의 embedding과 knowledge extraction은 공개 provider를 사용한다. k3s에서 접근하는
`100.66.249.76`의 self-hosted endpoint를 EKS에서 접근 가능하다고 가정하지 않는다.
기존 DB의 Settings override는 환경변수보다 우선하므로 provider 변경 시 함께 확인한다.

## 최초 배포 순서

1. `agent-memory`의 S3 Pod Identity 지원 코드를 검증·릴리즈하고, 해당 이미지 tag를
   GitOps `alpha`·`prod` values에 반영한다. 기존 `v0.28.14` 이미지는 정적 S3 키를 요구한다.
2. `terraform-env-demo/demo/4-role`을 plan/apply하여 두 S3 policy와 Memory role을 만든다.
   이어서 `demo/5-eks`를 plan/apply하여 Memory Pod Identity를 연결한다.
   `demo/9-agent-studio`의 plan에서 S3 비공개 설정과 k3s policy attachment 변경을 확인한다.
   기존 EC2·volume·bucket의 교체나 삭제 없이 적용한다. k3s의 cert-manager에는
   `opsp.dev` hosted zone의 DNS-01 권한이 필요하다. 옛 `mcp-memory` Bedrock policy·role은
   EKS의 해당 Pod Identity association을 먼저 제거한 뒤 삭제한다.
3. 이 저장소에서 EKS 연결 Secret을 확인하고, 없을 때만 생성한다.

   ```bash
   python3 bootstrap_agent_platform.py --cluster eks-demo
   python3 bootstrap_agent_platform.py --cluster eks-demo --apply
   ```

   생성 대상은 `agent-studio/postgres-password`, `agent-studio/database-url`,
   `agent-memory/database-url`, `agent-memory/neo4j-password`, `agent-memory/neo4j-auth`,
   `agent-memory/metrics-bearer-token`이다. 값은 SecureString으로 전달하고 로그에 출력하지 않는다.
   기존 값은 덮어쓰지 않으며, 서로 맞지 않는 부분 설정은 변경 없이 거부한다.
   OAuth·provider·암호화·scan token은 기존 `/k8s/common/agent-*` 경로를 사용한다.
4. 승인된 Git 변경을 반영하고 EKS `apps-eks`를 Sync하여 PostgreSQL·Neo4j ApplicationSet을 등록한다.
   `postgresql-eks-demo`, `neo4j-eks-demo`를 먼저 Sync하고 Secret·PVC·서비스 readiness를 확인한다.
5. k3s의 `traefik-gateway-k3s`를 Sync하여 새 `opsp.dev` 호스트와 인증서를 준비한다.
   `agent-studio-k3s`, `agent-memory-k3s`를 Sync하고 새 도메인과 OAuth를 확인한다.
6. `agent-studio-eks-demo`, `agent-memory-eks-demo`를 수동 Sync한다. 앱 자동 Sync 설정은
   변경하지 않는다. 기존 DB·MinIO 데이터는 유지한다.
7. EKS 앱의 내부 health와 Host 기반 라우팅을 확인한 뒤 `demo/3-alb`의 plan/apply로
   `studio.opspresso.com`, `memory.opspresso.com`의 기존 A 레코드를 import하여 ALB alias로
   전환하고 `*.opspresso.com` ACM 인증서를 연결한다. DNS 전환은 EKS 준비 후 수행한다.

## 검증

```bash
GITHUB_PUSH=false bash build.sh
python3 validate.py
pytest
```

Memory의 readiness `/api/health`는 PostgreSQL·schema·Neo4j를 검사한다. Liveness는
TCP로 검사하여 공유 DB 장애가 모든 Pod의 재시작으로 이어지지 않게 한다.
Memory HPA는 CPU 지표를 사용하고, Studio HPA는 `agent_studio_active_runs`를 사용한다.
Memory ServiceMonitor는 전용 `METRICS_BEARER_TOKEN`으로 인증한다.

배포 후에는 Argo CD health와 함께 각 앱의 DB readiness, S3/MinIO 쓰기·읽기·정리,
Memory 문서 처리, Studio audio·workspace worker, OAuth 로그인, Prometheus scrape를 확인한다.
Health 응답만으로 object storage·provider·worker 처리 성공을 판정하지 않는다.
