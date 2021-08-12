# Helm Charts Version

## Helm Repos

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add autoscaler https://kubernetes.github.io/autoscaler
helm repo add aws-ebs-csi-driver https://kubernetes-sigs.github.io/aws-ebs-csi-driver
helm repo add aws-efs-csi-driver https://kubernetes-sigs.github.io/aws-efs-csi-driver
helm repo add chaoskube https://linki.github.io/chaoskube
helm repo add dashboard https://kubernetes.github.io/dashboard
helm repo add datadog https://helm.datadoghq.com
helm repo add deliveryhero https://charts.deliveryhero.io
helm repo add eks https://aws.github.io/eks-charts
helm repo add external-secrets https://external-secrets.github.io/kubernetes-external-secrets
helm repo add fluxcd https://charts.fluxcd.io
helm repo add gocd https://gocd.github.io/helm-chart
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add incubator https://charts.helm.sh/incubator
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add jetstack https://charts.jetstack.io
helm repo add prometheus https://prometheus-community.github.io/helm-charts
helm repo add stable https://charts.helm.sh/stable
```

```bash
helm repo update

helm search repo "argo/argo-cd" -o json | jq .
helm search repo "argo/argo-rollouts" -o json | jq .
helm search repo "argo/argocd-notifications" -o json | jq .
helm search repo "autoscaler/cluster-autoscaler" -o json | jq .
helm search repo "aws-ebs-csi-driver/aws-ebs-csi-driver" -o json | jq .
helm search repo "aws-efs-csi-driver/aws-efs-csi-driver" -o json | jq .
helm search repo "chaoskube/chaoskube" -o json | jq .
helm search repo "dashboard/kubernetes-dashboard" -o json | jq .
helm search repo "datadog/datadog" -o json | jq .
helm search repo "deliveryhero/cluster-overprovisioner" -o json | jq .
helm search repo "eks/aws-load-balancer-controller" -o json | jq .
helm search repo "external-secrets/kubernetes-external-secrets" -o json | jq .
helm search repo "ingress-nginx/ingress-nginx" -o json | jq .
helm search repo "jetstack/cert-manager" -o json | jq .
helm search repo "stable/metrics-server" -o json | jq .
```
