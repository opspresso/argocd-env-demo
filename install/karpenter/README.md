# karpenter

* <https://karpenter.sh/docs/getting-started/>

## generate values.yaml

```bash
export AWS_DEFAULT_REGION="ap-northeast-2"
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CLUSTER_NAME="eks-demo"
export CLUSTER_ENDPOINT=$(aws eks describe-cluster --name $CLUSTER_NAME --query "cluster.endpoint" --output text)

# replace values.yaml
cp values.yaml values.output.yaml
find . -name values.output.yaml -exec sed -i "" -e "s/ACCOUNT_ID/${ACCOUNT_ID}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/AWS_DEFAULT_REGION/${AWS_DEFAULT_REGION}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/CLUSTER_NAME/${CLUSTER_NAME}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s@CLUSTER_ENDPOINT@${CLUSTER_ENDPOINT}@g" {} \;
```

## Install Karpenter

```bash
# helm repo add karpenter https://charts.karpenter.sh

# helm repo update
# helm search repo karpenter

helm upgrade --install karpenter karpenter/karpenter \
  -n addon-karpenter --create-namespace \
  -f values.output.yaml \
  --wait # wait for webhook

# helm uninstall karpenter -n addon-karpenter
```

## Install Karpenter Provisioner

```bash
kubectl apply -f provisioner.yaml --validate=false

# kubectl delete -f provisioner.yaml
```

## create app

```bash
kubectl create deployment inflate \
  --image=public.ecr.aws/eks-distro/kubernetes/pause:3.2

kubectl scale deployment inflate --replicas 10

kubectl patch configmap config-logging -n addon-karpenter --patch '{"data":{"loglevel.controller":"debug"}}'

kubectl logs -f -n addon-karpenter $(kubectl get pods -n addon-karpenter -l karpenter=controller -o name)

# kubectl delete deployment inflate
```
