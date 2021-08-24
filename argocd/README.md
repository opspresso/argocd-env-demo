# argocd

* <https://argo-cd.readthedocs.io/en/stable/getting_started/>

## generate secrets

> argocd admin password 를 잊어버리지 않기 위해, aws ssm 에 저장해 놓습니다. 그리고 그것을 base64 인코딩해서 argocd-secret.yaml 에 넣습니다.
> github 계정으로 인증학 위해 client id 와 client secret 을 각각 argocd-cm.yaml 와 argocd-secret.yaml 에 넣습니다.
> github org (opspresso) 에 team (sre) 을 만들고 권한을 부여하기 위해 argocd-rbac-cm.yaml 에 관련 내용을 입력 합니다.

```bash
ADMIN_USERNAME="admin"
ADMIN_PASSWORD="xxxx"

GITHUB_SECRET="xxxx"
GITHUB_WEBHOOK="xxxx"
SLACK_TOKEN="xxxx"

ARGOCD_PASSWORD="$(htpasswd -nbBC 10 "" ${ADMIN_PASSWORD} | tr -d ':\n' | sed 's/$2y/$2a/')"
ARGOCD_MTIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# put aws ssm param
aws ssm put-parameter --name /k8s/common/admin-user --value "${ADMIN_USERNAME}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/admin-password --value "${ADMIN_PASSWORD}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-password --value "${ARGOCD_PASSWORD}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/argocd-mtime --value "${ARGOCD_MTIME}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/github-secret --value "${GITHUB_SECRET}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/github-webhook --value "${GITHUB_WEBHOOK}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/slack-token --value "${SLACK_TOKEN}" --type SecureString --overwrite | jq .

# get aws ssm param
ADMIN_PASSWORD=$(aws ssm get-parameter --name /k8s/common/admin-password --with-decryption | jq .Parameter.Value -r)
ARGOCD_MTIME=$(aws ssm get-parameter --name /k8s/common/argocd-mtime --with-decryption | jq .Parameter.Value -r)
ARGOCD_PASSWORD=$(aws ssm get-parameter --name /k8s/common/argocd-password --with-decryption | jq .Parameter.Value -r)
GITHUB_SECRET=$(aws ssm get-parameter --name /k8s/common/github-secret --with-decryption | jq .Parameter.Value -r)
GITHUB_WEBHOOK=$(aws ssm get-parameter --name /k8s/common/github-webhook --with-decryption | jq .Parameter.Value -r)

# replace values-argocd.yaml
cp values-argocd.yaml values-argocd.output.yaml
find . -name values-argocd.output.yaml -exec sed -i "" -e "s/ARGOCD_MTIME/${ARGOCD_MTIME}/g" {} \;
find . -name values-argocd.output.yaml -exec sed -i "" -e "s@ARGOCD_PASSWORD@${ARGOCD_PASSWORD}@g" {} \;
find . -name values-argocd.output.yaml -exec sed -i "" -e "s/GITHUB_SECRET/${GITHUB_SECRET}/g" {} \;
find . -name values-argocd.output.yaml -exec sed -i "" -e "s/GITHUB_WEBHOOK/${GITHUB_WEBHOOK}/g" {} \;
```

## Install Argo CD

> Argocd 를 설치 합니다.
> addons 를 위해 ApplicationSet 도 함께 설치 합니다.

```bash
kubectl create ns argocd

helm repo update
helm upgrade argocd argoproj/argo-cd -n argocd -f values-argocd.output.yaml
# helm install argocd-applicationset argoproj/argocd-applicationset -n argocd

# kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/v2.1.0/manifests/install.yaml
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj-labs/applicationset/v0.2.0/manifests/install.yaml
```

## Change the argocd-server service type to LoadBalancer

> aws 에 elb 가 생성 되었습니다. port 와 acm 을 설정 합니다.

```bash
kubectl get svc argocd-server -n argocd
```

```
NAME            TYPE           CLUSTER-IP      EXTERNAL-IP                       PORT(S)                      AGE
argocd-server   LoadBalancer   172.20.41.157   xxx-000.apne2.elb.amazonaws.com   80:30080/TCP,443:30443/TCP   64m
```

* https://ap-northeast-2.console.aws.amazon.com/ec2/v2/home?region=ap-northeast-2#LoadBalancers:sort=loadBalancerName

```
Load Balancer Protocol    Load Balancer Port    Instance Protocol    Instance Port    Cipher    SSL Certificate
HTTP                      80                    HTTP                 30080            N/A       N/A
HTTPS                     443                   HTTPS                30443                      xxxx-xxxx-xxxx-xxxx-xxxx (ACM)
```

## argocd login

> argocd 에 로그인 합니다.
> cluster 를 add 합니다.

```bash
argocd login argocd.bruce.spic.me --grpc-web

argocd cluster list
argocd cluster add eks-demo

argocd repo list
# argocd repo add https://github.com/opspresso/argocd-env-demo --type git --name env-demo
# argocd repo add https://opspresso.github.io/helm-charts --type helm --name opspresso
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
