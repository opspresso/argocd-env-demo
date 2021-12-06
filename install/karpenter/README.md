# karpenter

* <https://karpenter.sh/docs/getting-started/>

```bash
export CLUSTER_NAME="eks-demo"
export AWS_DEFAULT_REGION='ap-northeast-2'
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
```

## Create the KarpenterNode IAM Role

```bash
# TEMPOUT=$(mktemp)
# curl -fsSL https://karpenter.sh/docs/getting-started/cloudformation.yaml > $TEMPOUT \
# && aws cloudformation deploy \
#   --stack-name Karpenter-${CLUSTER_NAME} \
#   --template-file ${TEMPOUT} \
#   --capabilities CAPABILITY_NAMED_IAM \
#   --parameter-overrides ClusterName=${CLUSTER_NAME}

# eksctl create iamidentitymapping \
#   --username system:node:{{EC2PrivateDNSName}} \
#   --cluster  ${CLUSTER_NAME} \
#   --arn arn:aws:iam::${AWS_ACCOUNT_ID}:role/KarpenterNodeRole-${CLUSTER_NAME} \
#   --group system:bootstrappers \
#   --group system:nodes
```

## Provisioner

* <https://karpenter.sh/docs/provisioner-crd/>

```bash
cat <<EOF | kubectl apply -f -
apiVersion: karpenter.sh/v1alpha5
kind: Provisioner
metadata:
  name: workers-v1
spec:
  requirements:
    - key: karpenter.sh/capacity-type
      operator: In
      values: ["spot"]
  limits:
    resources:
      cpu: 2000
  provider:
    instanceProfile: ${CLUSTER_NAME}-workers-v1
  ttlSecondsAfterEmpty: 30
EOF
```

## First Use

```bash
cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inflate
spec:
  replicas: 0
  selector:
    matchLabels:
      app: inflate
  template:
    metadata:
      labels:
        app: inflate
    spec:
      terminationGracePeriodSeconds: 0
      containers:
        - name: inflate
          image: public.ecr.aws/eks-distro/kubernetes/pause:3.2
          resources:
            requests:
              cpu: 1
EOF

kubectl scale deployment inflate --replicas 5

kubectl logs -f -n addon-karpenter $(kubectl get pods -n addon-karpenter -l karpenter=controller -o name)
```
