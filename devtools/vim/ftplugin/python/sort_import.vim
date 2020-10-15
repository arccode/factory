" Copyright 2016 The Chromium OS Authors. All rights reserved.
" Use of this source code is governed by a BSD-style license that can be
" found in the LICENSE file.
"
" Sort python imports
" we only care about python3
"
" According to python coding style, the import lines are sorted by package
" path, for example::
"
"   from cros.factory.test.device import info
"   from cros.factory.test import pytests
"
" rather than::
"
"   from cros.factory.test import pytests
"   from cros.factory.test.device import info
"
" Also, according to coding style, the following import style is not
" recommended::
"
"   from cros.factory.utils.sync_utils import (FunctionA,
"                                              FunctionB,
"                                              FunctionC)
"
" We should use either::
"
"   from cros.factory.utils.sync_utils import FunctionA
"   from cros.factory.utils.sync_utils import FunctionB
"   from cros.factory.utils.sync_utils import FunctionC
"
" Or::
"
"   from cros.factory.utils import sync_utils
"
" And use `sync_utils.FunctionA`, `sync_utils.FunctionB`, ... in your code.
"
" Therefore, we assume that each line is either in format:
"   from ... import ...
" or
"   import ...
if has('python')
  command! -range -nargs=* VimPython <line1>,<line2>python <args>
elseif has('python3')
  command! -range -nargs=* VimPython <line1>,<line2>python3 <args>
else
  echoerr "sort_import plugin will not work because the version of vim" .
      \ " supports neither python nor python3"
  finish
endif

if !exists('g:vim_sort_import_map')
  let g:vim_sort_import_map = '<Leader>si'
endif

if g:vim_sort_import_map != ''
  execute "vnoremap <buffer>" g:vim_sort_import_map
      \ ":VimPython SortImports()<CR>"
endif

VimPython <<EOF
import vim

def SortImports():
  text_range = vim.current.range

  def _ImportLineToKey(line):
    line, unused_sep, unused_rest = line.partition(' as ')
    if line.startswith('import '):
      return line.replace('import ', '').lower()
    return line.replace('from ', '').replace(' import ', '.').lower()
  text_range[:] = sorted(text_range, key=_ImportLineToKey)
EOF
