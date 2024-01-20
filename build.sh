#!/bin/bash
set -eux

GITHUB_PUSH=${GITHUB_PUSH:-false}

SHELL_DIR=$(dirname $0)

USERNAME=${CIRCLE_PROJECT_USERNAME:-opspresso}
REPONAME=${CIRCLE_PROJECT_REPONAME:-helm-charts}

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
  git config --global user.name "${GIT_USERNAME}"
  git config --global user.email "${GIT_USEREMAIL}"

  git add .
  git commit -m "Publish addons"

  git push -q https://${GITHUB_TOKEN}@github.com/${USERNAME}/${REPONAME}.git main
fi
