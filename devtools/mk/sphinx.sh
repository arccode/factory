#!/bin/bash
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
. "${SCRIPT_DIR}/common.sh" || exit 1

: "${SPHINX_VENV:="${SCRIPT_DIR}/sphinx.venv"}"
: "${SPHINX_REQUIREMENTS:="${SCRIPT_DIR}/sphinx.requirements.txt"}"

remove_py2_venv() {
  if [[ -d "${SPHINX_VENV}" && -f "${SPHINX_VENV}/bin/python2" ]]; then
    echo "Outdated Python2 venv detected, removing ${SPHINX_VENV}..."
    rm -rf "${SPHINX_VENV}"
  fi
}

load_venv() {
  if ! [ -d "${SPHINX_VENV}" ]; then
    echo "Cannot find '${SPHINX_VENV}', install virtualvenv"
    mkdir -p "${SPHINX_VENV}"
    # Include system site packages for packages like "yaml", "mox".
    virtualenv --system-site-package -p python3 "${SPHINX_VENV}"
  fi

  source "${SPHINX_VENV}/bin/activate"

  # pip freeze --local -r REQUIREMENTS.txt outputs something like:
  #   required_package_1==A.a
  #   required_package_2==B.b
  #   ## The following requirements were added by pip freeze:
  #   added_package_1==C.c
  #   added_package_2==D.d
  #   ...
  #
  #   required_pacakge_x are packages listed in REQUIREMENTS.txt,
  #   which are packages we really care about.
  if ! diff <(pip freeze --local -r "${SPHINX_REQUIREMENTS}" | \
      sed -n '/^##/,$ !p') "${SPHINX_REQUIREMENTS}" ; then
    pip install --force-reinstall -r "${SPHINX_REQUIREMENTS}"
  fi
}

main(){
  local make="$1"
  local doc_tmp_dir="$2"

  remove_py2_venv
  load_venv

  "${make}" -C "${doc_tmp_dir}" html

  mk_success
}

main "$@"
