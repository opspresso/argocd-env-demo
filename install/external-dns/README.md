# external-dns

## generate values.yaml

```bash
export ACCOUNT_ID=$(aws sts get-caller-identity | grep "Account" | cut -d'"' -f4)
export CLUSTER_NAME="eks-demo"

# replace values.yaml
cp values.yaml values.output.yaml
find . -name values.output.yaml -exec sed -i "" -e "s/ACCOUNT_ID/${ACCOUNT_ID}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/CLUSTER_NAME/${CLUSTER_NAME}/g" {} \;
```

## Install External DNS

```bash
# helm repo add external-dns https://kubernetes-sigs.github.io/external-dns

# helm repo update
# helm search repo external-dns

kubectl create ns addon-external-dns

helm install external-dns external-dns/external-dns -n addon-external-dns -f values.output.yaml

# helm upgrade external-dns external-dns/external-dns -n addon-external-dns -f values.output.yaml
```

* <https://console.aws.amazon.com/route53/v2/hostedzones>
