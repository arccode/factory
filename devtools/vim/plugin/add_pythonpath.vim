" Copyright 2016 The Chromium OS Authors. All rights reserved.
" Use of this source code is governed by a BSD-style license that can be
" found in the LICENSE file.
"
" Add py_pkg to PYTHONPATH, so jedi and YCM could work.
let py_pkg_dir = join([g:localrc_project_root, 'py_pkg'], '/')
if isdirectory(py_pkg_dir)
  if empty($PYTHONPATH)
    let $PYTHONPATH = py_pkg_dir
  else
    let $PYTHONPATH = py_pkg_dir . ':' . $PYTHONPATH
  endif
endif
