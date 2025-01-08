#!/bin/bash
set -eux

GITHUB_PUSH=${GITHUB_PUSH:-false}

SHELL_DIR=$(dirname $0)

USERNAME=${CIRCLE_PROJECT_USERNAME:-opspresso}
REPONAME=${CIRCLE_PROJECT_REPONAME:-helm-charts}

GIT_USERNAME="nalbam-bot"
GIT_USEREMAIL="bot@nalbam.com"

mkdir -p ${SHELL_DIR}/target

# find charts
LIST=$(ls charts)

for V in ${LIST}; do
  echo
  echo "Processing.. $V"
  python3 gen_values.py -r $V
done

git diff
git diff >${SHELL_DIR}/target/git_diff.txt

COUNT=$(cat ${SHELL_DIR}/target/git_diff.txt | wc -l | xargs)

if [ "x${COUNT}" != "x0" ]; then
  # commit message
  printf "$(date +%Y%m%d-%H%M)" >${SHELL_DIR}/target/commit_message.txt
fi
