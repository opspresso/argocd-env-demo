# multi architecture

name | image | amd64 | arm64
--- | --- | --- | ---
argo-rollouts | quay.io/argoproj/argo-rollouts | ✅ | ✅
argocd | quay.io/argoproj/argocd | ✅ | ❌ [PR](https://github.com/argoproj/argo-cd/pull/6758)
argocd-applicationset | quay.io/argoproj/argocd-applicationset | ✅ | ❌
argocd-notifications | argoprojlabs/argocd-notifications | ✅ | ✅
aws-ebs-csi-driver | amazon/aws-ebs-csi-driver | ✅ | ✅
aws-efs-csi-driver | amazon/aws-efs-csi-driver | ✅ | ✅
aws-load-balancer-controller | 602401143452.dkr.ecr.us-west-2.amazonaws.com/amazon/aws-load-balancer-controller | ✅ | ✅
aws-node | 602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/amazon-k8s-cni | ✅ | ✅
aws-node-termination-handler | public.ecr.aws/aws-ec2/aws-node-termination-handler | ✅ | ✅
cert-manager | quay.io/jetstack/cert-manager-controller | ✅ | ✅
chaoskube | quay.io/linki/chaoskube | ✅ | ❌
cluster-autoscaler | k8s.gcr.io/autoscaling/cluster-autoscaler | ✅ | ✅
coredns | 602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/eks/coredns | ✅ | ✅
dex | ghcr.io/dexidp/dex | ✅ | ✅
external-dns | k8s.gcr.io/external-dns/external-dns | ✅ | ✅
external-secrets | ghcr.io/external-secrets/kubernetes-external-secrets | ✅ | ✅
grafana | grafana/grafana | ✅ | ✅
irsa-operator | ghcr.io/voodooteam/irsa-operator | ✅ | ❌
istio | gcr.io/istio-testing/pilot / querycapistio/pilot | ✅ | ✅
kiali | quay.io/kiali/kiali | ✅ | ✅
kube-proxy | 602401143452.dkr.ecr.ap-northeast-2.amazonaws.com/eks/kube-proxy | ✅ | ✅
kube-state-metrics | k8s.gcr.io/kube-state-metrics/kube-state-metrics | ✅ | ✅
kubernetes-dashboard | kubernetesui/dashboard | ✅ | ✅
loki | grafana/loki | ✅ | ✅
metrics-server | k8s.gcr.io/metrics-server-amd64 / k8s.gcr.io/metrics-server-arm64 | ✅ | ✅
prometheus | quay.io/prometheus/prometheus | ✅ | ✅
promtail | grafana/promtail | ✅ | ✅