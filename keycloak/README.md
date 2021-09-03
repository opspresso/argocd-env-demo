# keycloak

## generate secrets

```bash
KEYCLOAK_GITHUB_CLIENT_ID="REPLACE_ME"
KEYCLOAK_GITHUB_CLIENT_SECRET="REPLACE_ME"

GOOGLE_CLIENT_ID="REPLACE_ME"
GOOGLE_CLIENT_SECRET="REPLACE_ME"

# put aws ssm param
aws ssm put-parameter --name /k8s/common/keycloak-github-id --value "${KEYCLOAK_GITHUB_CLIENT_ID}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/keycloak-github-secret --value "${KEYCLOAK_GITHUB_CLIENT_SECRET}" --type SecureString --overwrite | jq .

aws ssm put-parameter --name /k8s/common/google-id --value "${GOOGLE_CLIENT_ID}" --type SecureString --overwrite | jq .
aws ssm put-parameter --name /k8s/common/google-secret --value "${GOOGLE_CLIENT_SECRET}" --type SecureString --overwrite | jq .

# get aws ssm param
KEYCLOAK_GITHUB_CLIENT_ID=$(aws ssm get-parameter --name /k8s/common/keycloak-github-id --with-decryption | jq .Parameter.Value -r)
KEYCLOAK_GITHUB_CLIENT_SECRET=$(aws ssm get-parameter --name /k8s/common/keycloak-github-secret --with-decryption | jq .Parameter.Value -r)

GOOGLE_CLIENT_ID=$(aws ssm get-parameter --name /k8s/common/google-id --with-decryption | jq .Parameter.Value -r)
GOOGLE_CLIENT_SECRET=$(aws ssm get-parameter --name /k8s/common/google-secret --with-decryption | jq .Parameter.Value -r)

# replace realm.json
cp realm.json realm.output.json
find . -name realm.output.json -exec sed -i "" -e "s/KEYCLOAK_GITHUB_CLIENT_ID/${KEYCLOAK_GITHUB_CLIENT_ID}/g" {} \;
find . -name realm.output.json -exec sed -i "" -e "s/KEYCLOAK_GITHUB_CLIENT_SECRET/${KEYCLOAK_GITHUB_CLIENT_SECRET}/g" {} \;

find . -name realm.output.json -exec sed -i "" -e "s/GOOGLE_CLIENT_ID/${GOOGLE_CLIENT_ID}/g" {} \;
find . -name realm.output.json -exec sed -i "" -e "s/GOOGLE_CLIENT_SECRET/${GOOGLE_CLIENT_SECRET}/g" {} \;
```

* https://ap-northeast-2.console.aws.amazon.com/secretsmanager/home?region=ap-northeast-2#!/listSecrets

```bash
# /k8s/common/keycloak-realm
aws secretsmanager create-secret --name /k8s/common/keycloak-realm --secret-string file://realm.output.json
aws secretsmanager get-secret-value --secret-id /k8s/common/keycloak-realm | jq .
aws secretsmanager update-secret --secret-id /k8s/common/keycloak-realm --secret-string file://realm.output.json
```
