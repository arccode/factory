" Copyright 2016 The Chromium OS Authors. All rights reserved.
" Use of this source code is governed by a BSD-style license that can be
" found in the LICENSE file.
"
" Convert Chinese traditional characters into Chinese simplified characters.
" You can simply "<CTRL-v>" select some words, and "<Leader>cn" to convert
" these words.
"
if exists('g:chromeos_factory_iconv')
  finish
endif
let g:chromeos_factory_iconv = 1

execute "vnoremap <buffer> <Leader>cn :call ConvertZHToCN()<CR>"

function ConvertZHToCN()
  " pipe current selected content through
  " iconv -f UTF8 -t BIG5 | iconv -f BIG5 -t GB2312 | iconv -f GB2312 -t UTF8
  :'<,'>!iconv -f UTF8 -t BIG5 | iconv -f BIG5 -t GB2312 |
        \ iconv -f GB2312 -t UTF8
endfunction
