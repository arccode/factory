<!--
   -Copyright 2016 The Chromium OS Authors. All rights reserved.
   -Use of this source code is governed by a BSD-style license that can be
   -found in the LICENSE file.
-->
# ChromeOS Factory Developer VIM Plugins

This folder contains VIM plugins that are useful for ChromeOS Factory
development.

## Installation

Run `./setup.sh` to install script loader into your vim config.  If your `.vim`
folder or `.vimrc` file is not in default location (`~/.vim` and `~/.vimrc`),
you can use `DOT_VIM=... VIMRC=... ./setup.sh` to change it.

## Plugins
* `devtools/vim/ftplugin/python/sort_import.vim`
    - sort python import lines
* `devtools/vim/ftplugin/python/pylint.vim`
    - config pylint arguments for
    [scrooloose/syntastic](https://github.com/scrooloose/syntastic)
* `devtools/vim/ftplugin/python/basic.vim`
    - basic setup (indent, tabs, etc...)
* `devtools/vim/plugin/add_pythonpath.vim`
    - add factory files into PYTHONPATH (for
    [Valloric/YouCompleteMe](https://github.com/Valloric/YouCompleteMe) or
    [davidhalter/jedi-vim](https://github.com/davidhalter/jedi-vim))
* `devtools/vim/autoload/localrc.vim`
    - `.local.vimrc` loader
* `devtools/vim/plugin/iconv.vim`
    - convert selected traditional Chinese string into simplified Chinese.
