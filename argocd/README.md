# argocd

* <https://argo-cd.readthedocs.io/en/stable/getting_started/>

## Install Argo CD

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

## show secret

```bash
# put aws ssm param
aws ssm put-parameter --name /k8s/common/argocd-password --value "xxxx" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/github-secret --value "xxxx" --type SecureString --overwrite | jq .

# argocd-password
PASSWORD=$(aws ssm get-parameter --name /k8s/common/argocd-password --with-decryption | jq .Parameter.Value -r)
echo "$(htpasswd -nbBC 10 "" ${PASSWORD} | tr -d ':\n' | sed 's/$2y/$2a/')" | base64

# argocd-mtime
echo "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" | base64

# github-secret
aws ssm get-parameter --name /k8s/common/github-secret --with-decryption | jq .Parameter.Value -r | base64
```

## save argocd congifmap, secret

```bash
kubectl apply -n argocd -f argocd-secret.yaml
kubectl apply -n argocd -f argocd-cm.yaml
```

## Change the argocd-server service type to LoadBalancer

```bash
kubectl patch svc argocd-server -n argocd -p '{"spec": {"type": "LoadBalancer"}}'

kubectl get svc argocd-server -n argocd
```

```
NAME            TYPE           CLUSTER-IP      EXTERNAL-IP                                PORT(S)                      AGE
argocd-server   LoadBalancer   172.20.41.157   xxx-000.ap-northeast-2.elb.amazonaws.com   80:30081/TCP,443:30069/TCP   64m
```

```
Load Balancer Protocol    Load Balancer Port    Instance Protocol    Instance Port    Cipher    SSL Certificate
HTTP                      80                    HTTP                 30081            N/A       N/A
HTTPS                     443                   HTTPS                30069                      281ab87d-f28b-43db-b4d2-b4759950c369 (ACM)
```
