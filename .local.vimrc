" Copyright 2016 The Chromium OS Authors. All rights reserved.
" Use of this source code is governed by a BSD-style license that can be
" found in the LICENSE file.
"
" To load this file, You can symlink 'mk/vim/autoload/localrc.vim' to your
" .vim/autoload folder, and add "call localrc#load()" to your vimrc.
"
" Or, you can source this file directly in your vimrc.
"
if exists('g:loaded_chromeos_factory_localrc')
  finish
endif
let g:loaded_chromeos_factory_localrc = 1

let g:localrc_project_root = expand('<sfile>:h')

" Other files are placed under factory/devtools/vim
exec 'set rtp^=' . join([g:localrc_project_root, 'devtools', 'vim'], '/')
exec 'set rtp+=' . join([g:localrc_project_root, 'devtools', 'vim', 'after'], '/')
