#!/usr/bin/env bash
# Copyright 2016 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# Usage: DOT_VIM=<path/to/.vim> VIMRC=<path/to/vimrc> ./setup.sh
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"

: ${DOT_VIM:="${HOME}/.vim"}
DOT_VIM="$(readlink -f "${DOT_VIM}")"
echo ".vim/ is: ${DOT_VIM}"
mkdir -p "${DOT_VIM}/autoload"
if [ -e "${DOT_VIM}/autoload/localrc.vim" ]; then
  read -p \
      "localrc.vim is already in .vim/, do you want to override it? [y/N] " \
      answer
else
  read -p "Add localrc.vim to .vim/? [y/N] " answer
fi
if [ "${answer}" == "y" -o "${answer}" == "Y" ]; then
  rm -f "${DOT_VIM}/autoload/localrc.vim"
  ln -s "${SCRIPT_DIR}/autoload/localrc.vim" "${DOT_VIM}/autoload"
else
  echo "skipped..."
fi

: ${VIMRC:="${HOME}/.vimrc"}
VIMRC="$(readlink -f "${VIMRC}")"
echo ".vimrc is: ${VIMRC}"
read -p "Can we add 'call localrc#load()' into your vimrc? [y/N] " answer
if [ "${answer}" == "y" -o "${answer}" == "Y" ]; then
  echo "call localrc#load()" >>"${VIMRC}"
else
  echo "skipped..."
fi
