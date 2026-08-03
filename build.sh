#!/bin/bash
#
# Renders charts/*/values-template.yaml.j2 against every env/*.yaml.

set -euo pipefail

GITHUB_PUSH=${GITHUB_PUSH:-false}

SHELL_DIR=$(dirname "$0")

GIT_USERNAME="nalbam-bot"
GIT_USEREMAIL="bot@nalbam.com"

cd "${SHELL_DIR}"

# find charts
for CHART in charts/*/; do
  echo
  echo "Processing.. $(basename "${CHART}")"
  python3 gen_values.py -r "$(basename "${CHART}")"
done

if [ "${GITHUB_PUSH}" == "true" ]; then
  git config user.name "${GIT_USERNAME}"
  git config user.email "${GIT_USEREMAIL}"

  git add --all

  if git diff --cached --quiet; then
    echo
    echo "Nothing to commit."
    exit 0
  fi

  echo
  echo "Pushing to GitHub..."

  git commit -m "$(date +%Y%m%d-%H%M)"
  git push origin "HEAD:${MAIN_BRANCH:-main}"
fi
