#!/bin/bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
. "${SCRIPT_DIR}/common.sh" || exit 1

: ${BUNDLE_FACTORY_FLOW:=}

bundle_install() {
  local bundle_dir="$1"
  local src="$2"
  local dir="$3"
  local symlinks="$4"
  local src_name="$(basename "${src}")"
  local name

  mkdir -p "${bundle_dir}/${dir}"
  cp -f "${src}" "${bundle_dir}/${dir}"

  for name in ${symlinks}; do
    ln -sf "${src_name}" "${bundle_dir}/${dir}/${name}"
  done
}

main() {
  if [ "$#" != 6 ]; then
    die "Usage: $0 bundle_dir toolkit par doc_zip setup sysroot"
  fi

  local bundle_dir="$1"
  local toolkit="$2"
  local par="$3"
  local doc_zip="$4"
  local setup="$5"
  local sysroot="$6"
  local par_name="$(basename "${par}")"

  echo "Creating factory bundle in ${bundle_dir}..."
  mkdir -p "${bundle_dir}"
  bundle_install "${bundle_dir}" "${doc_zip}" .
  # TODO(hungte) The folder for toolkit should be 'factory_toolkit', but it will
  # currently conflict with make_factory_toolkit and the creation of bundle in
  # chromite. To prevent that, we'll name this 'toolkit' for a short time, until
  # the transition is complete.
  bundle_install "${bundle_dir}" "${toolkit}" toolkit
  bundle_install "${bundle_dir}" "${par}" shopfloor \
    "shopfloor shopfloor_server"
  if [ -n "${BUNDLE_FACTORY_FLOW}" ]; then
    bundle_install "${bundle_dir}" "${par}" factory_flow \
      "factory_flow finalize_bundle test_factory_flow"
  fi

  rsync -aL --exclude testdata "${setup}/" "${bundle_dir}/setup/"
  mkdir -p "${bundle_dir}/setup/bin"
  cp -f /usr/bin/cgpt "${bundle_dir}/setup/bin"
  cp -f /usr/bin/futility "${bundle_dir}/setup/bin"

  # TODO(hungte) Remove the copied cros-regions.json when regions.py supports
  # reading region database from local folder inside PAR.
  cp -f "${sysroot}/usr/share/misc/cros-regions.json" \
    "${bundle_dir}/shopfloor/."

  mk_success
}
main "$@"
