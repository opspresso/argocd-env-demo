# argocd

* <https://argo-cd.readthedocs.io/en/stable/getting_started/>

## Install Argo CD

> Argocd 를 설치 합니다.
> addons 를 위해 ApplicationSet 도 함께 설치 합니다.

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj-labs/applicationset/master/manifests/install.yaml
```

## show secret

> argocd admin password 를 잊어버리지 않기 위해, aws ssm 에 저장해 놓습니다. 그리고 그것을 base64 인코딩해서 argocd-secret.yaml 에 넣습니다.
> github 계정으로 인증학 위해 client id 와 client secret 을 각각 argocd-cm.yaml 와 argocd-secret.yaml 에 넣습니다.
> github org (opspresso) 에 team (sre) 을 만들고 권한을 부여하기 위해 argocd-rbac-cm.yaml 에 관련 내용을 입력 합니다.

```bash
# put aws ssm param
aws ssm put-parameter --name /k8s/common/admin-user --value "admin" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/admin-password --value "xxxx" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/github-secret --value "xxxx" --type SecureString --overwrite | jq .

# admin-password
PASSWORD=$(aws ssm get-parameter --name /k8s/common/admin-password --with-decryption | jq .Parameter.Value -r)
ADMIN_PASSWORD="$(htpasswd -nbBC 10 "" ${PASSWORD} | tr -d ':\n' | sed 's/$2y/$2a/' | base64)"

# admin-mtime
ADMIN_PASSWORD_MTIME="$(date -u +"%Y-%m-%dT%H:%M:%SZ" | base64)"

# github-secret
GITHUB_CLIENT_SECRET=$(aws ssm get-parameter --name /k8s/common/github-secret --with-decryption | jq .Parameter.Value -r | base64)

# replace argocd-secret.yaml
find . -name argocd-secret.yaml -exec sed -i "" -e "s/ADMIN_PASSWORD/${ADMIN_PASSWORD}/g" {} \;
find . -name argocd-secret.yaml -exec sed -i "" -e "s/ADMIN_PASSWORD_MTIME/${ADMIN_PASSWORD_MTIME}/g" {} \;
find . -name argocd-secret.yaml -exec sed -i "" -e "s/GITHUB_CLIENT_SECRET/${GITHUB_CLIENT_SECRET}/g" {} \;
```

## save argocd congifmap, secret

> 모두 apply 합니다.

```bash
kubectl apply -n argocd -f argocd-secret.yaml
kubectl apply -n argocd -f argocd-cm.yaml
kubectl apply -n argocd -f argocd-rbac-cm.yaml
```

## Change the argocd-server service type to LoadBalancer

> argocd 에 접속 하기 위해 service 를 LoadBalancer 타입으로 변경 합니다.
> aws 에 elb 가 생성 되어있음을 알 수 있습니다. port 와 ssm 을 설정 합니다.

```bash
kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "LoadBalancer"}}'

kubectl get svc argocd-server -n argocd
```

```
NAME            TYPE           CLUSTER-IP      EXTERNAL-IP                       PORT(S)                      AGE
argocd-server   LoadBalancer   172.20.41.157   xxx-000.apne2.elb.amazonaws.com   80:30081/TCP,443:30069/TCP   64m
```

```
Load Balancer Protocol    Load Balancer Port    Instance Protocol    Instance Port    Cipher    SSL Certificate
HTTP                      80                    HTTP                 30081            N/A       N/A
HTTPS                     443                   HTTPS                30069                      xxxx-xxxx-xxxx-xxxx-xxxx (ACM)
```

## argocd login

> argocd 에 로그인 합니다.
> cluster 를 add 합니다. repo 도 add 합니다.

```bash
argocd login argocd.bruce.spic.me --grpc-web

argocd cluster list
argocd cluster add eks-demo

argocd repo list
argocd repo add https://github.com/opspresso/argocd-env-demo --type git --name env-demo
argocd repo add https://opspresso.github.io/helm-charts --type helm --name opspresso
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
