# Kubernetes Workspace 운영

`agent-studio-workspaces` namespace의 실행 Pod 하나가 Workspace 하나를 담당한다. 앱·worker는
해당 namespace의 Pod get/list/create/delete와 exec만 사용할 수 있다. 실행 Pod에는 서비스 계정
토큰·운영 Secret·호스트 경로를 mount하지 않는다. CPU·메모리·emptyDir·ephemeral-storage는
Agent Studio 실행기가 제한하며 namespace quota는 EKS 32개, k3s 2개의 실행 Pod를 허용한다.

NetworkPolicy는 ingress와 egress를 기본 거부한다. cluster DNS와 public HTTP/HTTPS만 허용하며
사설망·다른 Pod·metadata endpoint는 차단한다. 폐쇄망이나 내부 모델은
`workspace_allow_public: false`와 `workspace_extra_egress`에 정확한 목적지·포트를 선언한다.
현재 DNS 허용 주소는 EKS `172.20.0.10/32`, k3s `10.43.0.10/32`다.
두 클러스터는 IPv4를 사용하므로 CIDR 허용 규칙도 IPv4로만 구성한다. IPv6는 기본 차단을 유지한다.

## 디스크와 메모리

Kubernetes 실행의 `/workspace`, `/control`, `/tmp`와 이미지 캐시는 전용 노드의 ephemeral 디스크를
사용한다. EKS `WORKSPACE_DISK_MB=2048`에서는 Pod당 4608Mi를 예약·제한하며 namespace의
32개 Pod 상한은 144Gi 예약량이다. 현재 Workspace NodeClass의 노드별 디스크는 160Gi다. 이미지·호스트
로그는 이 Pod 예약량과 별개이므로 node-exporter 파일시스템과 kubelet 사용량을 함께 확인한다.

파일과 native Session은 암호화한 체크포인트로 복원한다. Pod별 영구 PVC는 만들지 않으며,
Pod 삭제·퇴거 시 마지막 체크포인트 이후의 파일은 복구되지 않는다. `emptyDir.sizeLimit`은
즉시 쓰기를 막는 quota가 아니라 kubelet 퇴거 기준이다. EBS PVC는 이 보존 계약을 바꾸거나
더 큰 작업 디스크가 필요할 때 별도로 설계한다. CNI의 커널 메모리 누수는 PVC로 해결되지 않는다.

`workspace_storage`는 Kubernetes 실행 Pod가 아니라 보존된 DinD 복구용 PVC의 용량이다.
EKS 실행 메모리는 2Gi로 설정하며 한도 초과는 cgroup OOM과 Workspace 중단으로 확인한다.

EKS worker는 2 replicas이며 각각 native 작업 16개와 Chat 후속 실행 2개를 처리한다.
체크포인트 저장·복원은 프로세스당 2개로 제한한다. EKS와 k3s는 `workspace_legacy_docker: false`로
Kubernetes 실행기만 사용한다. 추가 ConfigMap 입력의 checksum으로 앱과 worker가 함께 새 설정을 읽는다.
새 지표와 동시성 설정을 지원하는 Studio 이미지를 먼저 배포한 뒤 이 chart를 sync한다.

## 승인 후 전환 순서

1. 각 Agent의 Workspace 도구를 꺼서 신규 접수를 막고 기존 Workspace를 정상 종료한다.
   worker가 체크포인트를 저장하고 모든 Docker Workspace 컨테이너를 제거했는지 확인한다.
   worker Pod를 먼저 내리거나 `agent_studio_maintenance`로 전체 writer를 중지하면 기존 DinD 작업을 잃을 수 있다.
2. 새 Kubernetes 백엔드와 `workspace-migration-check.cjs`, `tini`, UID 검사를 포함하는 앱·Sandbox 이미지를
   같은 릴리스로 게시한다. phase의 이미지 태그는 기존 GitOps 릴리스 절차로 갱신한다.
3. EKS는 승인된 Terraform 변경으로 `5-eks` output → `6-eks-node`의 `workspaces` NodeClass/NodePool을 준비한다.
   기존 EKS network policy controller와 metrics addon을 확인한다. k3s는 기본 network policy controller를 유지한다.
4. 앱 chart를 sync한다. PreSync는 legacy Pod 목록과 Docker 컨테이너 목록을 조회한다.
   컨테이너가 남아 있거나 daemon/API에 연결할 수 없으면 전환을 차단한다. 이 검사는 1번의 접수 차단을 대신하지 않는다.
5. 앱·worker의 Kubernetes RBAC, task namespace의 ECR Secret, Pod 실행·취소·체크포인트·복원을 확인한 뒤
   Workspace 도구를 다시 켠다. k3s의 새 namespace도 ESO ECR generator를 사용하며 기존 EC2 역할로 인증한다.

Docker에서 처음 전환하는 설치는 기존 핸들의 조회·정리가 끝날 때까지
`workspace_legacy_docker: true`를 사용한다. 이때 legacy daemon은 worker 수와 독립적으로
1개만 실행하며, sync wave 1에서 기존 worker 교체 후 PVC를 연다.

기존 Docker 참조와 컨테이너가 없고 Kubernetes 실행·체크포인트 복원 검사가 통과하면,
승인된 정리에서 `workspace_legacy_docker: false`로 전환한다. Service와 전용 NetworkPolicy는
GitOps가 제거한다. 자동 prune을 막은 기존 daemon Deployment는 새 앱·worker가 Ready이고
`WORKSPACE_LEGACY_DOCKER=false`를 읽는 것을 확인한 뒤 운영자가 삭제한다.

복구용 PVC와 ECR generator/ExternalSecret은 `Prune=false,Delete=false`로 계속 보존한다.
PVC·체크포인트의 데이터 삭제는 별도 승인이 필요하다. ECR 인증은 앱과 Kubernetes 실행 Pod도 사용한다.

## 검증

`scripts/validate.py`와 pytest는 양쪽 플랫폼의 렌더·RBAC·quota·보존·drain gate를 확인한다.
Agent Studio의 `test:workspace:kubernetes`에 이 chart의 k3s 렌더를 제공하면 일회용 로컬 k3s에서
실제 exec, 제한된 계정, 통신 차단, DNS, quota, 디스크 퇴거와 체크포인트 복원을 검사한다.

배포 후에는 Pod `reason`과 이벤트, Workspace `interrupted` 상태, worker heartbeat와 고아 정리 로그를 확인한다.
EKS Prometheus와 k3s Alloy/Grafana Cloud의 상태 지표·경보 구성은 `argocd-env-addons`가 소유한다.
운영 노드 장애·디스크 압박 시험은 별도 승인으로 제한된 테스트 Workspace에만 수행한다.
