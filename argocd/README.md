# argocd

* <https://argo-cd.readthedocs.io/en/stable/getting_started/>

### eks create

* <https://github.com/opspresso/terraform-env-demo/tree/main/25-eks-demo>

```bash
terraform apply
```

## generate values.yaml

> argocd admin password 를 잊어버리지 않기 위해, aws ssm 에 저장 합니다.
> github 계정으로 인증학 위해 client id 와 client secret 을 저장 합니다.
> github org (opspresso) 에 team (sre) 을 만들고 권한을 부여 합니다.

```bash
ARGOCD_HOSTNAME="argocd.demo.spic.me"
GITHUB_ORG="daangn"
GITHUB_TEAM="sre"

# replaceable values
ADMIN_PASSWORD="REPLACE_ME"
ARGOCD_PASSWORD="$(htpasswd -nbBC 10 "" ${ADMIN_PASSWORD} | tr -d ':\n' | sed 's/$2y/$2a/')"
ARGOCD_SERVER_SECRET="REPLACE_ME" # random string
ARGOCD_GITHUB_ID="REPLACE_ME" # github OAuth Apps <https://github.com/organizations/opspresso/settings/applications>
ARGOCD_GITHUB_SECRET="REPLACE_ME" # github OAuth Apps
ARGOCD_WEBHOOK="REPLACE_ME" # random string
ARGOCD_NOTI_TOKEN="REPLACE_ME" # xoxp-xxxx <https://api.slack.com/apps>

# put aws ssm param
aws ssm put-parameter --name /k8s/common/admin-password --value "${ADMIN_PASSWORD}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-password --value "${ARGOCD_PASSWORD}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-server-secret --value "${ARGOCD_SERVER_SECRET}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-github-id --value "${ARGOCD_GITHUB_ID}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-github-secret --value "${ARGOCD_GITHUB_SECRET}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-webhook --value "${ARGOCD_WEBHOOK}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-noti-token --value "${ARGOCD_NOTI_TOKEN}" --type SecureString --overwrite | jq .

# get aws ssm param
ADMIN_PASSWORD=$(aws ssm get-parameter --name /k8s/common/admin-password --with-decryption | jq .Parameter.Value -r)
ARGOCD_PASSWORD=$(aws ssm get-parameter --name /k8s/common/argocd-password --with-decryption | jq .Parameter.Value -r)
ARGOCD_MTIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
ARGOCD_SERVER_SECRET=$(aws ssm get-parameter --name /k8s/common/argocd-server-secret --with-decryption | jq .Parameter.Value -r)
ARGOCD_GITHUB_ID=$(aws ssm get-parameter --name /k8s/common/argocd-github-id --with-decryption | jq .Parameter.Value -r)
ARGOCD_GITHUB_SECRET=$(aws ssm get-parameter --name /k8s/common/argocd-github-secret --with-decryption | jq .Parameter.Value -r)
ARGOCD_WEBHOOK=$(aws ssm get-parameter --name /k8s/common/argocd-webhook --with-decryption | jq .Parameter.Value -r)

AWS_ACM_CERT="$(aws acm list-certificates --query "CertificateSummaryList[].{CertificateArn:CertificateArn,DomainName:DomainName}[?contains(DomainName,'${ARGOCD_HOSTNAME}')] | [0].CertificateArn" | jq . -r)"

# replace values.yaml
cp values.yaml values.output.yaml
find . -name values.output.yaml -exec sed -i "" -e "s/ARGOCD_HOSTNAME/${ARGOCD_HOSTNAME}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s@ARGOCD_PASSWORD@${ARGOCD_PASSWORD}@g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/ARGOCD_MTIME/${ARGOCD_MTIME}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/ARGOCD_SERVER_SECRET/${ARGOCD_SERVER_SECRET}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/ARGOCD_GITHUB_ID/${ARGOCD_GITHUB_ID}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/ARGOCD_GITHUB_SECRET/${ARGOCD_GITHUB_SECRET}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/ARGOCD_WEBHOOK/${ARGOCD_WEBHOOK}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/GITHUB_ORG/${GITHUB_ORG}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s/GITHUB_TEAM/${GITHUB_TEAM}/g" {} \;
find . -name values.output.yaml -exec sed -i "" -e "s@AWS_ACM_CERT@${AWS_ACM_CERT}@g" {} \;
```

## Install Argo CD

> Argocd 를 설치 합니다.
> addons 를 위해 ApplicationSet 도 함께 설치 합니다.

```bash
helm repo update
helm search repo argo-cd

kubectl create ns argocd

helm install argocd argo/argo-cd -n argocd -f values.output.yaml
helm install argocd-applicationset argo/argocd-applicationset -n argocd

helm upgrade argocd argo/argo-cd -n argocd -f values.output.yaml
helm upgrade argocd-applicationset argo/argocd-applicationset -n argocd

# kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.1.0/manifests/install.yaml
# kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj-labs/applicationset/v0.2.0/manifests/install.yaml
```

## Change the argocd-server service type to LoadBalancer

> aws 에 elb 가 생성 되었습니다. route53 에서 argocd.demo.spic.me 와 연결해 줍니다.

```bash
kubectl get pod -n argocd
kubectl get svc argocd-server -n argocd
```

```
NAME            TYPE           CLUSTER-IP      EXTERNAL-IP                       PORT(S)                      AGE
argocd-server   LoadBalancer   172.20.41.157   xxx-000.apne2.elb.amazonaws.com   80:30080/TCP,443:30443/TCP   64m
```

* https://console.aws.amazon.com/route53/v2/hostedzones#
* https://argocd.demo.spic.me

## argocd login

> argocd 에 로그인 합니다.
> cluster 를 add 합니다.

```bash
argocd login argocd.demo.spic.me --grpc-web

argocd cluster list
argocd cluster add eks-demo
```

## addons

> addons 를 등록 합니다.

```bash
kubectl apply -n argocd -f https://raw.githubusercontent.com/opspresso/argocd-env-demo/main/addons.yaml
```

## apps

> apps 를 등록 합니다.

```bash
kubectl apply -n argocd -f https://raw.githubusercontent.com/opspresso/argocd-env-demo/main/apps.yaml
```

## 삭제

### service 및 aws elb 삭제

> service 를 삭제 하여, LoadBalancer 로 생성한 elb 를 삭제 합니다.

```bash
kubectl delete svc -n argocd argocd-server
```

### terraform destory

```bash
terraform destory
```
