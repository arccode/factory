" Copyright 2016 The Chromium OS Authors. All rights reserved.
" Use of this source code is governed by a BSD-style license that can be
" found in the LICENSE file.
"
" Find and source local vimrc files in each parent directory.  The order of
" finding and sourcing files is from parent to child.  Therefore, if the
" directory structure is:
"
"   project_root
"   |-- a
"   |   |-- b
"   |   |   `-- .local.vimrc
"   |   `-- .local.vimrc
"   `-- .local.vimrc
"
" Then the order of loading .local.vimrc is::
"
"   source project_root/.local.vimrc
"   source project_root/a/.local.vimrc
"   source project_root/a/b/.local.vimrc
"
" To use this script, copy this script to .vim/autoload/localrc.vim
" And in your vimrc, add::
"
"   call localrc#load()
"
let s:save_cpo = &cpo
set cpo&vim

let g:localrc_default_depth = -1  " unlimited
let g:localrc_filename = '.local.vimrc'

function! localrc#load(...)
  " filename we would like to load
  let fname = 1 <= a:0 ? a:1 : g:localrc_filename

  " If starting point is not given, will use working directory
  let search_dir = 2 <= a:0 ? a:2 : getcwd()

  " If max search depth is not given, use the default one
  let max_depth = 3 <= a:0 ? a:3 : g:localrc_default_depth

  for filepath in s:search(fname, search_dir, max_depth)
    source `=filepath`
  endfor
endfunction

function! s:search(fname, current_dir, depth)
  " expand to full path
  let current_dir = fnamemodify(a:current_dir, ':p')

  " maximum depth to search for a localrc
  let depth = a:depth

  " current path ends with '/', remove it
  if current_dir =~ '\/$'
    let current_dir = fnamemodify(current_dir, ':h')
  endif

  let found_files = []

  while depth != 0
    for fpath in split(globpath(current_dir, a:fname, 1), "\n")
      if filereadable(fpath)
        let found_files = [fpath] + found_files
      endif
    endfor

    let depth -= 1
    if current_dir == '/'
      break
    else
      let current_dir = fnamemodify(current_dir, ':h')
    endif
  endwhile

  return found_files
endfunction

let &cpo = s:save_cpo
unlet s:save_cpo
