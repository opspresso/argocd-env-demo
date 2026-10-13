# 서비스 용량과 DB 연결 예산

현재 실행 환경은 k3s alpha입니다. `eks-demo` prod는 미래 클러스터를 위한 선언이며
현재 EKS 노드·서비스가 운영 중이라는 뜻이 아닙니다. k3s 노드는 `m6i.xlarge`, 메모리 16Gi이며
현재 사용량은 배포 때 다시 확인합니다. k3s에는 compute requests/limits나 HPA를 선언하지 않습니다.
PVC 용량과 Forge Pod/Job 수 제한은 유지합니다.

## 미래 EKS 선언

| 워크로드 | requests CPU / memory | memory limit | 확장 |
| --- | --- | --- | --- |
| Studio web | 100m / 512Mi | 2Gi | 2~6, active Agent 실행 8/Pod·app CPU 70% |
| Studio Workspace observer | 200m / 512Mi | 2Gi | 2, 프로세스당 원격 작업 관찰 16개·대화 재개 2개 |
| Studio Audio observer | 100m / 256Mi | 2Gi | 1 |
| Memory web | 100m / 256Mi | 512Mi | 2~6, app CPU 70% |
| Librio web | 100m / 512Mi | 2Gi | 2, app CPU 70% |
| Librio queue worker | 200m / 512Mi | 2Gi | 1, web과 분리 |
| Forge controller/gateway/worker | 100m / 512Mi | 2Gi | 2, app CPU 70% |
| PostgreSQL | 250m / 768Mi | 2Gi | 단일 StatefulSet, 400 connections |
| Forge Sandbox | 1 / 2Gi | 2Gi | namespace에서 최대 Pod32·Job32 |

Studio의 active execution metric은 Studio Agent 실행을 나타냅니다. native 모델 요청은
Forge가 별도 집계합니다. Istio sidecar CPU는 앱 CPU에 합산하지 않습니다.
노드 수 계산은 sidecar·DaemonSet·rolling surge와 가장 큰 노드 한 대 손실까지 포함해야 합니다.
낮은 유휴 CPU만으로 production 기준 노드를 줄이지 않습니다.

## PostgreSQL

네 앱은 같은 `agent_platform` DB를 사용합니다. 풀은 생성 여부보다 실제 동시 접속 가능 상한으로
계산합니다. 각 프로세스의 명시된 풀 크기는 다음과 같습니다.

| 프로세스 | ordinary | queue | readiness | content lock | AI admission | 합계 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Studio web | 4 | 0 | 1 | 4 | 0 | 9 |
| Studio Workspace/Audio observer | 4 | 0 | 0 | 4 | 0 | 8 |
| Memory web | 4 | 0 | 1 | 0 | 0 | 5 |
| Librio web | 4 | 2 | 1 | 0 | 9 | 16 |
| Librio worker | 4 | 2 | 0 | 0 | 9 | 15 |
| Forge | 12 | 0 | 0 | 0 | 0 | 12 |

Studio Workspace readiness는 별도 짧은 프로세스에서 1개 쿼리 연결을 사용합니다.
heartbeat liveness는 DB를 열지 않습니다. Librio maintenance lock은 ordinary pool에서
checkout하므로 추가 pool로 중복 계산하지 않습니다. worker health는 process-only입니다.

Librio AI admission pool9는 요청용8+정리/정책제어1 연결입니다. 전체8·batch4 제한은
공유 PostgreSQL에서 합산되며 interactive 용량을 남깁니다. pool을5로 줄이면 같은 프로세스의
batch4가 local admission 슬롯을 모두 점유할 수 있으므로 총량·batch 정책과 함께 조정해야 합니다.

| 환경 | 정상 최대 세대 | 2세대 rollout | 운영 여유 최소 | PostgreSQL 한도 |
| --- | ---: | ---: | ---: | ---: |
| alpha | `Studio(9+8+8+probe1)+Memory5+Librio(16+15)+Forge12 = 74` | 148 | 20 | 200 |
| 미래 EKS | `Studio(6×9+2×8+8+probe2)+Memory6×5+Librio(2×16+15)+Forge2×12 = 181` | 362 | 20 | 400 |

`test_production_capacity.py`는 실제 렌더의 HPA·worker replica·pool 값으로 이 상한을 계산합니다.
새 프로세스, HPA 상한, pool 크기를 바꾸면 함께 갱신합니다. 이전 rollout이 끝나기 전에 다음
rollout을 누적하지 않습니다. PostgreSQL `max_connections`·공유 메모리 설정 변경은 재시작이 필요합니다.
현재 shared buffers는256MB, work_mem은4MB입니다. `max_connections`가 모든 query의 메모리
상한을 보장하지는 않으므로 실제 쿼리 메모리·RSS·연결 대기 시간을 관찰합니다.

## 실행 용량과 보존

`workspace_max_pods`는 Forge 실행 namespace의 Pod/Job 상한입니다. Studio observer 동시성은
실행 자원 quota와 별개입니다. 실행 Pod는 일시적인 디스크를 사용하고 마지막 확정 checkpoint로 복원합니다.
EKS Pod당 4608Mi ephemeral storage 예약에 더해 이미지·호스트 로그 디스크가 필요합니다.
미래 Workspace NodePool은 taint `agent-forge/workspace`와 앱의 toleration을 맞춰야 합니다.

기존 Studio DinD PVC는 보존하지만 daemon은 시작하지 않습니다. 기존 PostgreSQL·MinIO·Neo4j
데이터를 새 서비스 namespace로 자동 복사하지 않습니다. DB·object storage는 단일 인스턴스이며
이 배포가 failover나 backup을 제공하지는 않습니다. 백업 복원과 실제 CNI 격리는 별도 검증합니다.
