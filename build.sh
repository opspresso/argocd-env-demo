#!/bin/bash

OS_NAME="$(uname | awk '{print tolower($0)}')"

SHELL_DIR=$(dirname $0)

USERNAME=${CIRCLE_PROJECT_USERNAME:-opspresso}
REPONAME=${CIRCLE_PROJECT_REPONAME:-argocd-env-demo}

BRANCH=${CIRCLE_BRANCH:-master}

TG_USERNAME="${1:-$TG_USERNAME}"
TG_PROJECT="${2:-$TG_PROJECT}"
TG_VERSION="${3:-$TG_VERSION}"

TG_PHASE="${4:-$TG_PHASE}"
TG_TYPE="${5:-$TG_TYPE}"

GIT_USERNAME="bot"
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

    _result "TG_PHASE=${TG_PHASE}"
    _result "TG_TYPE=${TG_TYPE}"

    if [ "${TG_USERNAME}" == "" ] || [ "${TG_PROJECT}" == "" ] || [ "${TG_VERSION}" == "" ]; then
        _success
    fi

    if [ ! -d "${SHELL_DIR}/apps/${TG_PROJECT}" ]; then
        _error "Not found ${TG_PROJECT}"
    fi

    _result "${TG_USERNAME}/${TG_PROJECT}:${TG_VERSION}"
}

_phase() {
    if [ "${PERSONAL_TOKEN}" == "" ]; then
        _error "Not found PERSONAL_TOKEN"
    fi

    # # version check
    # TMP=/tmp/releases
    # curl -sL "https://api.github.com/repos/${TG_USERNAME}/${TG_PROJECT}/releases" > ${TMP}
    # PRERELEASE="$(cat ${TMP} | jq -r --arg VERSION "${TG_VERSION}" '.[] | select(.tag_name==$VERSION) | "\(.draft) \(.prerelease)"')"

    # _result "PRERELEASE: \"${PRERELEASE}\""

    # # prerelease
    # if [ "${PRERELEASE}" != "false false" ]; then
    #     _success
    # fi

    # https://circleci.com/docs/api/v2/#get-a-pipeline-39-s-workflows
    CIRCLE_API="https://circleci.com/api/v2/project/gh/${USERNAME}/${REPONAME}/pipeline"
    CIRCLE_URL="${CIRCLE_API}?circle-token=${PERSONAL_TOKEN}"

    pushd ${SHELL_DIR}/apps/${TG_PROJECT}

    # find kustomize
    LIST=$(ls -d */kustomization.yaml | cut -d'/' -f1)

    for PHASE in ${LIST}; do
        _result "${PHASE} kustomize"

        if [ "${PHASE}" != "base" ]; then
            # build_parameters
            PAYLOAD="{\"parameters\":{"
            PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
            PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
            PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
            PAYLOAD="${PAYLOAD}\"phase\":\"${PHASE}\","
            PAYLOAD="${PAYLOAD}\"type\":\"kustomize\""
            PAYLOAD="${PAYLOAD}}}"

            _result "PAYLOAD=${PAYLOAD}"

            curl -X POST \
                -u ${PERSONAL_TOKEN}: \
                -H "Content-Type: application/json" \
                -d "${PAYLOAD}" "${CIRCLE_API}"
        fi
    done

    # find helm chart
    LIST=$(ls | grep 'values-' | grep '.yaml' | cut -d'.' -f1)

    for V in ${LIST}; do
        PHASE=${V:7}

        _result "${PHASE} helm"

        # build_parameters
        PAYLOAD="{\"parameters\":{"
        PAYLOAD="${PAYLOAD}\"username\":\"${TG_USERNAME}\","
        PAYLOAD="${PAYLOAD}\"project\":\"${TG_PROJECT}\","
        PAYLOAD="${PAYLOAD}\"version\":\"${TG_VERSION}\","
        PAYLOAD="${PAYLOAD}\"phase\":\"${PHASE}\","
        PAYLOAD="${PAYLOAD}\"type\":\"helm\""
        PAYLOAD="${PAYLOAD}}}"

        _result "PAYLOAD=${PAYLOAD}"

        curl -X POST \
            -u ${PERSONAL_TOKEN}: \
            -H "Content-Type: application/json" \
            -d "${PAYLOAD}" "${CIRCLE_API}"
    done

    popd
}

_build() {
    if [ "${TG_TYPE}" == "kustomize" ]; then
        if [ ! -f ${SHELL_DIR}/apps/${TG_PROJECT}/${TG_PHASE}/kustomization.yaml ]; then
            _error "Not found ${TG_PROJECT}/${TG_PHASE}/kustomization.yaml"
        fi
    elif [ "${TG_TYPE}" == "helm" ]; then
        if [ ! -f ${SHELL_DIR}/apps/${TG_PROJECT}/values-${TG_PHASE}.yaml ]; then
            _error "Not found ${TG_PROJECT}/values-${TG_PHASE}.yaml"
        fi
    else
        _error "${TG_PROJECT} ${TG_TYPE}"
    fi

    git config --global user.name "${GIT_USERNAME}"
    git config --global user.email "${GIT_USEREMAIL}"

    NEW_BRANCH="${TG_PROJECT}-${TG_PHASE}-${TG_VERSION}"
    MESSAGE="Deploy ${TG_PROJECT} ${TG_PHASE} ${TG_VERSION}"

    HAS="false"
    LIST="/tmp/branch-list"
    git branch -a > ${LIST}

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
    done < ${LIST}

    if [ "${HAS}" == "true" ]; then
        _success "${NEW_BRANCH}"
    fi

    HAS_DEV=$(echo ${TG_PHASE} | grep '\-dev' | wc -l | xargs)

    _command "git branch ${NEW_BRANCH} ${BRANCH}"
    git branch ${NEW_BRANCH} ${BRANCH}

    _command "git checkout ${NEW_BRANCH}"
    git checkout ${NEW_BRANCH}

    _command "replace ${TG_VERSION}"

    # replace
    _command "${TG_TYPE}.py -r ${TG_PROJECT} -p ${TG_PHASE} -n ${TG_USERNAME}/${TG_PROJECT} -v ${TG_VERSION}"
    python ${TG_TYPE}.py -r apps/${TG_PROJECT} -p ${TG_PHASE} -n ${TG_USERNAME}/${TG_PROJECT} -v ${TG_VERSION}

    _command "git add --all"
    git add --all

    _command "git commit -m ${MESSAGE}"
    git commit -m "${MESSAGE}"

    _command "git push github.com/${USERNAME}/${REPONAME} ${NEW_BRANCH}"
    git push -q https://${GITHUB_TOKEN}@github.com/${USERNAME}/${REPONAME}.git ${NEW_BRANCH}

    if [ "x${HAS_DEV}" == "x0" ]; then
        _command "hub pull-request -f -b ${USERNAME}:master -h ${USERNAME}:${NEW_BRANCH} --no-edit"
        hub pull-request -f -b ${USERNAME}:master -h ${USERNAME}:${NEW_BRANCH} --no-edit
    else
        _command "git checkout master"
        git checkout master

        _command "git merge ${NEW_BRANCH}"
        git merge ${NEW_BRANCH}

        _command "git push github.com/${USERNAME}/${REPONAME} master"
        git push -q https://${GITHUB_TOKEN}@github.com/${USERNAME}/${REPONAME}.git master
    fi
}

_prepare

if [ "${TG_PHASE}" == "" ]; then
    _phase
else
    _build
fi

_success
