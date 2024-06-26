#!/bin/bash

OS_NAME="$(uname | awk '{print tolower($0)}')"

SHELL_DIR=$(dirname $0)

PROVIDER=${1}

USERNAME=${CIRCLE_PROJECT_USERNAME:-opspresso}
REPONAME=${CIRCLE_PROJECT_REPONAME:-argocd-env-demo}

BRANCH=${CIRCLE_BRANCH:-main}

TG_USERNAME="${TG_USERNAME:-opspresso}"
TG_PROJECT="${TG_PROJECT:-sample}"
TG_VERSION="${TG_VERSION:-v0.0.0}"
TG_CONTAINER="${TG_CONTAINER:-app}"
TG_ACTION="${TG_ACTION}"
TG_PHASE="${TG_PHASE:-alpha}"
TG_TYPE="${TG_TYPE:-helm}"

GIT_USERNAME="nalbam-bot"
GIT_USEREMAIL="bot@nalbam.com"

################################################################################

# command -v tput > /dev/null && TPUT=true
TPUT=

_echo() {
  if [ "${TPUT}" != "" ] && [ "$2" != "" ]; then
    echo -e "$(tput setaf $2)$1$(tput sgr0)"
  else
    echo -e "$1"
  fi
}

_result() {
  echo
  _echo "# $@" 4
}

_command() {
  echo
  _echo "$ $@" 3
}

_success() {
  echo
  _echo "+ $@" 2
  exit 0
}

_error() {
  echo
  _echo "- $@" 1
  exit 1
}

_error_check() {
  RESULT=$?
  if [ ${RESULT} != 0 ]; then
    _error ${RESULT}
  fi
}

_replace() {
  if [ "${OS_NAME}" == "darwin" ]; then
    sed -i "" -e "$1" $2
  else
    sed -i -e "$1" $2
  fi
}

################################################################################

_prepare() {
  _result "TG_USERNAME=${TG_USERNAME}"
  _result "TG_PROJECT=${TG_PROJECT}"
  _result "TG_VERSION=${TG_VERSION}"
  _result "TG_CONTAINER=${TG_CONTAINER}"
  _result "TG_ACTION=${TG_ACTION}"
  _result "TG_PHASE=${TG_PHASE}"
  _result "TG_TYPE=${TG_TYPE}"

  if [ "${TG_USERNAME}" == "" ] || [ "${TG_PROJECT}" == "" ] || [ "${TG_VERSION}" == "" ]; then
    _success
  fi

  if [ ! -d "${SHELL_DIR}/charts/${TG_PROJECT}" ]; then
    _error "Not found ${TG_PROJECT}"
  fi

  _result "${TG_USERNAME}/${TG_PROJECT}:${TG_VERSION}"
}

_hook_action() {
  PHASE=$1
  TYPE=$2

  # https://docs.github.com/en/actions/reference/events-that-trigger-workflows

  _command "github dispatches : ${TG_PROJECT} ${TG_VERSION} ${PHASE} ${TG_ACTION}"

  # build_parameters
  PAYLOAD="{\"event_type\":\"gitops\","
  PAYLOAD="${PAYLOAD}\"client_payload\":{"
  PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
  PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
  PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
  PAYLOAD="${PAYLOAD}\"container\":\"${TG_CONTAINER}\","
  PAYLOAD="${PAYLOAD}\"action\":\"${TG_ACTION}\","
  PAYLOAD="${PAYLOAD}\"phase\":\"${PHASE}\","
  PAYLOAD="${PAYLOAD}\"type\":\"${TYPE}\""
  PAYLOAD="${PAYLOAD}}}"

  _result "PAYLOAD=${PAYLOAD}"

  curl -sL -X POST \
    -H "Accept: application/vnd.github.v3+json" \
    -H "Authorization: Bearer ${GITHUB_TOKEN}" \
    -d "${PAYLOAD}" \
    https://api.github.com/repos/${USERNAME}/${REPONAME}/dispatches

  sleep 2
}

_hook_circleci() {
  PHASE=$1
  TYPE=$2

  # https://circleci.com/docs/api/v2/#operation/listPipelinesForProject

  _command "circleci pipeline : ${TG_PROJECT} ${TG_VERSION} ${PHASE} ${TG_ACTION}"

  # build_parameters
  PAYLOAD="{\"parameters\":{"
  PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
  PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
  PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
  PAYLOAD="${PAYLOAD}\"container\":\"${TG_CONTAINER}\","
  PAYLOAD="${PAYLOAD}\"action\":\"${TG_ACTION}\","
  PAYLOAD="${PAYLOAD}\"phase\":\"${PHASE}\","
  PAYLOAD="${PAYLOAD}\"type\":\"${TYPE}\""
  PAYLOAD="${PAYLOAD}}}"

  _result "PAYLOAD=${PAYLOAD}"

  curl -sL -X POST \
    -u ${PERSONAL_TOKEN}: \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" \
    https://circleci.com/api/v2/project/gh/${USERNAME}/${REPONAME}/pipeline

  sleep 2
}

_phase_action() {
  if [ -z "${GITHUB_TOKEN}" ]; then
    _error "Not found GITHUB_TOKEN"
  fi

  pushd ${SHELL_DIR}/charts/${TG_PROJECT}

  # find helm chart
  # LIST=$(ls | grep 'values-' | grep '.yaml' | cut -d'.' -f1)
  LIST=$(ls | grep -E 'values-([a-z]+).yaml' | cut -d'.' -f1)

  for V in ${LIST}; do
    PHASE=${V:7}

    _result "[${PHASE}] helm"

    _hook_action ${PHASE} helm
  done

  # find kustomize
  LIST=$(ls -d */kustomization.yaml | cut -d'/' -f1)

  for PHASE in ${LIST}; do
    _result "[${PHASE}] kustomize"

    if [ "${PHASE}" != "base" ]; then
      _hook_action ${PHASE} kustomize
    fi
  done

  popd
}

_phase_circleci() {
  if [ "${PERSONAL_TOKEN}" == "" ]; then
    _error "Not found PERSONAL_TOKEN"
  fi

  pushd ${SHELL_DIR}/charts/${TG_PROJECT}

  # find helm chart
  # LIST=$(ls | grep 'values-' | grep '.yaml' | cut -d'.' -f1)
  LIST=$(ls | grep -E 'values-([a-z]+).yaml' | cut -d'.' -f1)

  for V in ${LIST}; do
    PHASE=${V:7}

    _result "[${PHASE}] helm"

    _hook_circleci ${PHASE} helm
  done

  # find kustomize
  LIST=$(ls -d */kustomization.yaml | cut -d'/' -f1)

  for PHASE in ${LIST}; do
    _result "[${PHASE}] kustomize"

    if [ "${PHASE}" != "base" ]; then
      _hook_circleci ${PHASE} kustomize
    fi
  done

  popd
}

_build() {
  if [ "${TG_TYPE}" == "kustomize" ]; then
    if [ ! -f ${SHELL_DIR}/charts/${TG_PROJECT}/${TG_PHASE}/kustomization.yaml ]; then
      _error "Not found ${TG_PROJECT}/${TG_PHASE}/kustomization.yaml"
    fi
  elif [ "${TG_TYPE}" == "helm" ]; then
    if [ ! -f ${SHELL_DIR}/charts/${TG_PROJECT}/values-${TG_PHASE}.yaml ]; then
      _error "Not found ${TG_PROJECT}/values-${TG_PHASE}.yaml"
    fi
  else
    _error "${TG_PROJECT} ${TG_TYPE}"
  fi

  git config --global user.name "${GIT_USERNAME}"
  git config --global user.email "${GIT_USEREMAIL}"

  git config pull.rebase true

  NEW_BRANCH="${TG_PROJECT}-${TG_PHASE}-${TG_VERSION}"
  MESSAGE="Deploy ${TG_PROJECT} ${TG_PHASE} ${TG_VERSION}"

  HAS="false"
  LIST="/tmp/branch-list"
  git branch -a >${LIST}

  while read VAR; do
    ARR=(${VAR})
    if [ -z ${ARR[1]} ]; then
      if [ "${ARR[0]}" == "${NEW_BRANCH}" ]; then
        HAS="true"
      fi
    else
      if [ "${ARR[1]}" == "${NEW_BRANCH}" ]; then
        HAS="true"
      fi
    fi
  done <${LIST}

  if [ "${HAS}" == "true" ]; then
    _success "${NEW_BRANCH}"
  fi

  # # has alpha or dev
  # HAS_DEV=$(echo "${TG_PHASE}" | grep -E '\-alpha$|\-dev$' | wc -l | xargs)

  # # has prod
  # HAS_PROD=$(echo "${TG_PHASE}" | grep -E '\-prod$' | wc -l | xargs)

  _command "git pull"
  git pull --rebase origin ${BRANCH}

  _command "replace ${TG_VERSION}"

  # replace
  _command "${TG_TYPE}.py -r ${TG_PROJECT} -p ${TG_PHASE} -n ${TG_USERNAME}/${TG_PROJECT} -v ${TG_VERSION} -c ${TG_CONTAINER} -a ${TG_ACTION}"
  python ${TG_TYPE}.py -r "${TG_PROJECT}" -p "${TG_PHASE}" -n "${TG_USERNAME}/${TG_PROJECT}" -v "${TG_VERSION}" -c "${TG_CONTAINER}" -a "${TG_ACTION}"

  _command "git add --all"
  git add --all

  _command "git commit -m ${MESSAGE}"
  git commit -m "${MESSAGE}"

  # # push
  # _command "git push github.com/${USERNAME}/${REPONAME} ${BRANCH}"
  # git push -q https://${GITHUB_TOKEN}@github.com/${USERNAME}/${REPONAME}.git ${BRANCH}

  # pr or push
  if [ "${TG_PHASE}" == "prod" ]; then
    _command "git branch ${NEW_BRANCH} ${BRANCH}"
    git branch ${NEW_BRANCH} ${BRANCH}

    _command "git checkout ${NEW_BRANCH}"
    git checkout ${NEW_BRANCH}

    _command "git push github.com/${USERNAME}/${REPONAME} ${NEW_BRANCH}"
    git push -q https://${GITHUB_TOKEN}@github.com/${USERNAME}/${REPONAME}.git ${NEW_BRANCH}

    _error_check

    _command "hub pull-request -f -b ${USERNAME}:${BRANCH} -h ${USERNAME}:${NEW_BRANCH} --no-edit"
    hub pull-request -f -b ${USERNAME}:${BRANCH} -h ${USERNAME}:${NEW_BRANCH} --no-edit
  else
    _command "git push github.com/${USERNAME}/${REPONAME} ${BRANCH}"
    git push -q https://${GITHUB_TOKEN}@github.com/${USERNAME}/${REPONAME}.git ${BRANCH}
  fi

  _error_check
}

_prepare

if [ "${TG_PHASE}" == "" ]; then
  if [ "${PROVIDER}" == "action" ]; then
    _phase_action
  elif [ "${PROVIDER}" == "circleci" ]; then
    _phase_circleci
  fi
else
  _build
fi

_success
