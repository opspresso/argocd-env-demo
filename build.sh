#!/bin/bash

GITHUB_PUSH=${GITHUB_PUSH:-false}

SHELL_DIR=$(dirname $0)

USERNAME=${CIRCLE_PROJECT_USERNAME:-opspresso}
REPONAME=${CIRCLE_PROJECT_REPONAME:-argocd-env-demo}

GIT_USERNAME="nalbam-bot"
GIT_USEREMAIL="bot@nalbam.com"

# find charts
LIST=$(ls charts)

for V in ${LIST}; do
  echo
  echo "Processing.. $V"
  python3 gen_values.py -r $V
done

if [ "${GITHUB_PUSH}" == "true" ]; then
  echo
  echo "Pushing to GitHub..."

  git config --global user.name "${GIT_USERNAME}"
  git config --global user.email "${GIT_USEREMAIL}"

  git add .
  git commit -m "$(date +%Y%m%d-%H%M)"

  git push -q https://${GITHUB_TOKEN}@github.com/${USERNAME}/${REPONAME}.git main
fi
