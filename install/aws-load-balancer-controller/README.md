# aws-load-balancer-controller

## generate values.yaml

```bash
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export CLUSTER_NAME="eks-demo"

# replace values.yaml
cp values.yaml values.output.yaml
find . -name values.output.yaml -exec sed -i "" -e "s/ACCOUNT_ID/${ACCOUNT_ID}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/CLUSTER_NAME/${CLUSTER_NAME}/g" {} \;
```

## Install

```bash
# helm repo add helm repo add eks https://aws.github.io/eks-charts

# helm repo update
# helm search repo aws-load-balancer-controller

helm upgrade --install aws-load-balancer-controller-${CLUSTER_NAME} eks/aws-load-balancer-controller \
  -n addon-aws-load-balancer-controller --create-namespace \
  -f values.output.yaml

# helm uninstall aws-load-balancer-controller-${CLUSTER_NAME} -n addon-aws-load-balancer-controller
```
