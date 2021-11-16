# argocd-autopilot

* <https://argocd-autopilot.readthedocs.io/en/stable/Getting-Started/>

## Install

```bash
brew install argocd-autopilot
```

## Personal access tokens

```bash
export GIT_TOKEN="REPLACE_ME" # Personal access tokens <https://github.com/settings/tokens>

aws ssm put-parameter --name /k8s/common/argocd-autopilot-token --value "${GIT_TOKEN}" --type SecureString --overwrite | jq .

export GIT_TOKEN=$(aws ssm get-parameter --name /k8s/common/argocd-autopilot-token --with-decryption | jq .Parameter.Value -r)
```
