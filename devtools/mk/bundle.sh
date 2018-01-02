#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
. "${SCRIPT_DIR}/common.sh" || exit 1

bundle_install() {
  local bundle_dir="$1"
  local src="$2"
  local dir="$3"
  local symlinks="$4"
  local src_name="$(basename "${src}")"
  local name output src_command

  mkdir -p "${bundle_dir}/${dir}"
  cp -f "${src}" "${bundle_dir}/${dir}"

  for name in ${symlinks}; do
    # Symlinks do not work well when builbot is packaging for factory.zip so we
    # want to create shell scripts instead.
    output="${bundle_dir}/${dir}/${name}"
    # shellcheck disable=SC2016
    src_command='"$(dirname "$(readlink -f "$0")")/'"${src_name}"'"'
    echo '#!/bin/sh' >"${output}"
    echo "${src_command} ${name} "'"$@"' >>"${output}"
    chmod a+rx "${output}"
  done
}

main() {
  if [ "$#" != 4 ]; then
    die "Usage: $0 bundle_dir toolkit par setup"
  fi
  # We want all files and directories created to be readable by world.
  umask 022

  local bundle_dir="$1"
  local toolkit="$2"
  local par="$3"
  local setup="$4"

  echo "Creating factory bundle in ${bundle_dir}..."
  mkdir -p "${bundle_dir}"
  bundle_install "${bundle_dir}" "${toolkit}" toolkit
  bundle_install "${bundle_dir}" "${par}" shopfloor \
    "factory_server"

  rsync -aL --exclude testdata "${setup}/" "${bundle_dir}/setup/"
  mkdir -p "${bundle_dir}/setup/bin"
  cp -f /usr/bin/cgpt "${bundle_dir}/setup/bin"
  cp -f /usr/bin/futility "${bundle_dir}/setup/bin"

  # Last chance to make sure all bundle files are world readable.
  chmod -R ugo+rX "${bundle_dir}"

  mk_success
}
main "$@"
