# Helm Charts Version

## Helm Repos

```bash
helm repo add argo https://argoproj.github.io/argo-helm
helm repo add autoscaler https://kubernetes.github.io/autoscaler
helm repo add aws-ebs-csi-driver https://kubernetes-sigs.github.io/aws-ebs-csi-driver
helm repo add aws-efs-csi-driver https://kubernetes-sigs.github.io/aws-efs-csi-driver
helm repo add chaoskube https://linki.github.io/chaoskube
helm repo add codecentric https://codecentric.github.io/helm-charts
helm repo add cortex https://cortexproject.github.io/cortex-helm-chart
helm repo add crossplane https://charts.crossplane.io/stable
helm repo add dashboard https://kubernetes.github.io/dashboard
helm repo add datadog https://helm.datadoghq.com
helm repo add deliveryhero https://charts.deliveryhero.io
helm repo add devtron https://helm.devtron.ai
helm repo add eks https://aws.github.io/eks-charts
helm repo add external-dns https://kubernetes-sigs.github.io/external-dns
helm repo add external-secrets https://external-secrets.github.io/kubernetes-external-secrets
helm repo add flagger https://flagger.app
helm repo add fluxcd https://charts.fluxcd.io
helm repo add gocd https://gocd.github.io/helm-chart
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add incubator https://charts.helm.sh/incubator
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo add irsa-operator https://voodooteam.github.io/irsa-operator
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo add jetstack https://charts.jetstack.io
helm repo add karpenter https://charts.karpenter.sh
helm repo add kiali https://kiali.org/helm-charts
helm repo add kubecost https://kubecost.github.io/cost-analyzer
helm repo add opspresso https://opspresso.github.io/helm-charts
helm repo add prometheus https://prometheus-community.github.io/helm-charts
helm repo add sealed-secrets https://bitnami-labs.github.io/sealed-secrets
helm repo add stable https://charts.helm.sh/stable
```

```bash
helm repo update

helm search repo "argo/argo-cd" -o json | jq .
helm search repo "autoscaler/cluster-autoscaler" -o json | jq .
helm search repo "dashboard/kubernetes-dashboard" -o json | jq .
```
