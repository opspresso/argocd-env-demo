# Production 용량 운영

`eks-demo`는 production이다. 현재 용량 목표는 동시에 활성화된 Workspace Pod 32개다.
실제 처리량은 모델 응답 시간·명령·파일 크기에 따라 달라지므로 이 수치를 사용자 수나 RPS로 해석하지 않는다.

## 예산과 확장

| 워크로드 | requests CPU / memory | limits CPU / memory | 확장 |
| --- | --- | --- | --- |
| Studio web | 100m / 512Mi | CPU ceiling 없음 / 2Gi | 2~6 replicas; 실행 부하 8/Pod 및 app CPU 70% |
| Workspace worker | 200m / 512Mi | 1 / 2Gi | 2 replicas × native 16개; Chat 후속 실행은 각각 2개 |
| Audio worker | 100m / 256Mi | 1 / 2Gi | 1 replica, 작업 큐·처리 지연 관찰 |
| Agent Memory | 100m / 256Mi | CPU ceiling 없음 / 512Mi | 2~6 replicas; app CPU 70% |
| PostgreSQL | 250m / 768Mi | 2 / 2Gi | 350 connections, shared buffers 256MB |
| Neo4j | 1 / 2Gi | 1 / 2Gi | heap 512Mi·page cache 512Mi; 쿼리 지연·GC 확인 |
| MCP 4개 | 각 chart의 자원 예산 | 각 chart의 메모리 한도 | 현재 각 1 replica; 다중화 전 세션·재연결 동작 검증 |
| sample-node | 100m / 128Mi | 100m / 256Mi | 2~12 replicas; app CPU 50% |
| sample Redis | 25m / 64Mi | CPU ceiling 없음 / 256Mi | 단일 인스턴스 |

Studio의 HPA는 `agent_studio_active_execution_requests`를 사용한다. 일반 Agent 실행과 native
Workspace 모델 요청을 합한 값이다. 별도 app CPU 신호는 파일 처리·요청 파싱·콘솔 부하를 포함한다.
Istio sidecar CPU를 앱 CPU에 합산하지 않는다. 종료 유예와 느린 scale-down은 진행 중인 실행을 보호한다.

DB 연결은 롤링 배포에서 구세대·신세대가 함께 살아 있는 상황까지 계산한다. Studio는 프로세스당
일반 pool 4개, readiness 1개, content lock 4개를 허용한다. Agent Memory는 10개다.
최대 replica의 두 세대는 282개, worker exec readiness는 최대 16개를 추가한다. 350개 중 나머지는
운영·초기화 여유다. `test_production_capacity.py`가 이 합계를 검사한다. 동시에 여러 세대의
배포를 누적하지 말고 이전 rollout의 종료를 확인한다.
Kubernetes worker는 제어 호출 상한 120초보다 긴 180초 종료 유예를 사용하여 lease를 넘긴다.

## Workspace 용량 변경

1. `env/eks-demo.yaml`의 `workspace_max_pods`, `workspace_worker_replicas`,
   `workspace_worker_concurrency`를 맞춘다. 현재 2 × 16 = 32다. 후속 Chat 동시성은
   `workspace_continuation_concurrency`로 별도 제한한다.
2. `terraform-env-demo/demo/6-eks-node`의 `workspace_max_pods`도 같은 값으로 계획한다.
   현재 4-CPU 노드당 실행 Pod 3개와 교체 여유 1개를 계산하여 CPU 48·메모리 192Gi 상한을 둔다.
   이 값은 예약 노드 수가 아니며 Auto Mode가 수요에 따라 노드를 만든다.
3. DB 연결·worker 메모리·AWS vCPU quota·subnet IP·노드 디스크 여유를 검사한다.
   기본 daemon, EKS의 관리형 NodeClass/NodePool을 별도 pool 대신 임의 변경하지 않는다.
4. NodePool 용량을 먼저 적용하고, PostgreSQL readiness·실제 설정을 확인한 뒤 앱 용량을 적용한다.
   PostgreSQL의 접속 수와 메모리 설정 변경은 재시작이 필요하다.
5. namespace quota, worker replica·환경변수, HPA `ScalingActive`, 새 노드의 Ready와
   Workspace 실행·취소·복원을 확인한다. production 노드 장애·디스크 압박 시험은 별도 승인으로 수행한다.

Pod는 1 CPU·2Gi 메모리·4608Mi ephemeral storage를 예약한다. node의 이미지 캐시·시스템 로그·
커널 메모리는 이 값 밖에 있으므로 호스트 메모리·파일시스템도 함께 감시한다.
quota가 차면 작업은 원래 실행 기한 안에서 대기한다. CPU·메모리·디스크 상한을 없애지 않는다.

## 저장과 가용성

Workspace 파일은 checkpoint로 복원하고 Pod 디스크는 일시적이다. `WORKSPACE_CHECKPOINT_HISTORY`
기본값 `retention`은 이전 checkpoint를 보존 기간까지 유지한다. `latest`는 최신 참조를 확정한 뒤
이전 checkpoint를 정리하며 기존 데이터 삭제 승인을 받은 뒤 선택한다. 최신 checkpoint 이후의
파일은 Pod 소실 시 복구되지 않는다. 별도의 DB·object storage backup은 계속 필요하다.

PostgreSQL·Neo4j·Redis는 현재 단일 인스턴스다. 이 설정은 트래픽·실행 용량 확장이고 DB failover를
제공하지 않는다. PVC 사용량·증가율과 query latency를 관찰하고, HA 전환은 복원 검증을 포함한
별도 데이터 이전으로 진행한다. 관측성 addon의 예산은 `argocd-env-addons/docs/production-capacity.md`가 소유한다.
