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
    rm -f "${output}"
    # shellcheck disable=SC2016
    src_command='"$(dirname "$(readlink -f "$0")")/'"${src_name}"'"'
    echo '#!/bin/sh' >"${output}"
    echo "${src_command} ${name} "'"$@"' >>"${output}"
    chmod a+rx "${output}"
  done
}

add_readme() {
  local dir="$1"
  local contents="$2"
  mkdir -p "${dir}"
  echo "${contents}" >"${dir}/README"
}

main() {
  if [[ "$#" != 5 ]]; then
    die "Usage: $0 bundle_dir toolkit par setup bin_root"
  fi
  # We want all files and directories created to be readable by world.
  umask 022

  local bundle_dir="$1"
  local toolkit="$2"
  local par="$3"
  local setup="$4"
  local bin_root="${5:-/}"

  echo "Creating factory bundle in ${bundle_dir}..."
  mkdir -p "${bundle_dir}"

  # Create README and dummy files.
  add_readme "${bundle_dir}/release_image" \
    "This folder is for release image, please put signed recovery image here."
  add_readme "${bundle_dir}/test_image" \
    "This folder is for test image."
  add_readme "${bundle_dir}/firmware" \
    "Put any firmware updater here or leave it empty to use the release image."
  add_readme "${bundle_dir}/hwid" \
    "This folder is for HWID bundle. Please download from CPFE and put here."
  # 'factory_shim' may be created by chromite so we cannot add README here.

  bundle_install "${bundle_dir}" "${toolkit}" toolkit
  rsync -aL --exclude testdata "${setup}/" "${bundle_dir}/setup/"

  # Replace symlinks
  bundle_install "${bundle_dir}" "${par}" \
    setup "image_tool"

  # Use lddtree if possible.
  if type lddtree >/dev/null 2>&1; then
    lddtree --root="${bin_root}" \
      --bindir=/ --libdir=/ \
      --generate-wrappers --copy-to-tree="${bundle_dir}/setup/libx64" \
      /usr/bin/cgpt /usr/bin/futility
    ln -s -t "${bundle_dir}/setup" "libx64/cgpt" "libx64/futility"
  else
    cp -f "${bin_root}"/usr/bin/cgpt "${bin_root}"/usr/bin/futility \
      "${bundle_dir}/setup"
  fi

  # Last chance to make sure all bundle files are world readable.
  chmod -R ugo+rX "${bundle_dir}"

  mk_success
}
main "$@"
