# Coding Style Guide

<http://goto/factory-style-guide>

<!--* freshness: { owner: 'stimim' reviewed: '2020-03-23' } *-->

[TOC]

There are lots of Google, Chromium, and Chromium OS style guides out there. The
ones most relevant for factory work are:

*   Python
    *   [Chromium OS Python style
        guide](https://chromium.googlesource.com/chromiumos/docs/+/HEAD/styleguide/python.md)
    *   [Python PEP-8 style guide](http://www.python.org/dev/peps/pep-0008/)
    *   [Google Python style guide
        (public)](https://google.github.io/styleguide/pyguide.html)
*   JavaScript:
    *   [Chromium Web Development style
        guide](https://chromium.googlesource.com/chromium/src/+/HEAD/styleguide/web/web.md)
    *   [Google JavaScript style guide
        (public)](https://google.github.io/styleguide/javascriptguide.xml)
*   HTML/CSS
    *   [Chromium Web Development style
        guide](https://chromium.googlesource.com/chromium/src/+/HEAD/styleguide/web/web.md)
    *   [Google HTML/CSS style guide
        (public)](https://google.github.io/styleguide/htmlcssguide.xml)

Help! Which one do I use?

First of all, don't sweat it too much. You do need to be familiar with the style
guides for the languages you use, but there's a lot of information in there and
you're not going to remember everything the first time. Try your best and use
common sense!

## Python

Follow the [Chromium OS Python style
guide](https://chromium.googlesource.com/chromiumos/docs/+/HEAD/styleguide/python.md),
which says that Chromium OS code should be "PEP-8 with exceptions". The biggest
exceptions are that,

*   We use `MixedCase` instead of `lower_case` for function names.
*   We use a 2-space indent instead of a 4-space indent.
    - The Chomium OS python style guide has changed to 4-space indent, but we
      are still using 2-space indent in factory projects.

[PEP-8](http://www.python.org/dev/peps/pep-0008/#descriptive-naming-styles) says
that acronyms are written in upper-case: `HTTPServerError` not
`HttpServerError`. We follow PEP-8 here.

You should also read and abide by the [Google Python style
guide](https://google.github.io/styleguide/pyguide.html), especially the
sections about
[comments](https://google.github.io/styleguide/pyguide.html?showone=Comments#Comments).
(The "official" Chromium OS policy says that the Google Python style guide isn't
an authority, but in general it has lots of good points and you should follow it
unless there is a strong reason not to do so.) There are a few places where you
need to ignore the Google Python style guide:

*   We use `MixedCase` instead of `lower_case` for function names.
*   We follow PEP-8 and write acronyms in upper-case: `HTTPServerError` not
    `HttpServerError`.
*   We use a 2-space indent instead of a 4-space indent.
*   We use pylint instead of pychecker.
*   You may use `#!/usr/bin/env python3` or `#!/usr/bin/python3` for shebang.

Finally, you must use pylint. In platform/factory, you can run `make lint` to do
this. platform/factory/Makefile has a blocklist for files that are not yet
pylint-compliant; if you make substantial changes to an existing file, please
fix lint problems and remove the file from the blocklist.

### **Shebang**

The recommended way is:

`#!/usr/bin/env python3`

Some of the factory code, for example setup/\*, need to run on a non-ChromiumOS
machine in factory. It may be any Linux distribution, or even Windows Box. So we
allow using env in shebang to reduce compatibility issues. However on Linux,
parameters in shebang when using env will be considered as file name for
execution, so we need to allow both (using env, or just python). See
<https://chromium-review.googlesource.com/265172> for some discussion.

### Temporary Files

Never use `tempfile.mkstemp` because it leaves an opened fd and would cause
leaks easily. Try the utility functions in `cros.factory.utils.files_utils`:
`CreateTemporaryFile` and `UnopenedTemporaryFile` first. (They are implemented
by `tempfile.NamedTemporaryFile(delete=False)`)

### Avoid bare-except

If you want to catch "most exceptions", do `except Exception:` instead of
`except:`, because the later one also catches `SystemExit` and
`KeyboardInterrupt`.

`make lint` should warn you about this.

### Naming unused variables

The existing guidelines didn't set a very precise rule about how to name unused
variables. There were some
[discussion](https://chromium-review.googlesource.com/#/c/409197/) and here's
our conclusion.

For variables inside a function, follow **`unused_*`** naming style.

For variables as function parameter (usually due to overriding methods in a
class), name as usual then **`del var`**, and del should be in the beginning of
that function.

Example:

```
class B(A):
  def DoSomething(self, myarg):
    del myarg  # unused
    ...
    fd, unused_fname = temp.mkstemp()
    writelog(fd)
    ...
```

### Header Cheat Sheet

For easy cutting-and-pasting, here's the header you should use for Python files
(based on
[this](https://chromium.googlesource.com/chromium/src/+/HEAD/styleguide/c++/c++.md#file-headers)).

```
#!/usr/bin/env python3
# Copyright 2020 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
```

**NOTE: `factory_common` has been removed ([b/112251287](http://b/112251287),
[CL:1837164](https://chromium-review.googlesource.com/c/chromiumos/platform/factory/+/1837164)).**

### Creating Command Line Tools

If there are no special reasons, a symbolic link should be created under `bin/`
folder. The symbolic link should be linked to **`../py/cli/factory_env.py`**.
And a file or symbolic link should be created under `py/cli/`, which is the real
implementation of the command line tool.  For example,

```
platform/factory
|-- bin/
|   `-- image_tool -> ../py/cli/factory_env.py
`-- py/
    |-- cli/
    |   |-- factory_env.py
    |   `-- image_tool.py -> ../tools/image_tool.py
    `-- tools/
        `-- image_tool.py
```

The `factory_env.py` script detects the real python script to execute
(`py/tools/image_tool.py` in this case), and inject the factory package folder
into system path before running the real python script.

### Import Ordering
Imports should be split into following sections:
1. System packages
2. Third party packages
3. Project (`cros.factory`) packages
4. `cros.factory.external` packages

In each section, import lines should be sorted, the sorting key for each import
line is constructued as following:

```
import a.b.c  # sorting key: 'a.b.c'
from x.y import z  # sorting key: 'x.y.z'

import a.b.c as xyz  # sorting key: 'a.b.c', "as xyz" is ignored.
from x.y import z as abc  # sorting key: 'x.y.z', "as abc" is ignored.
```

[sort_import.vim](devtools/vim/ftplugin/python/sort_import.vim) is a Vim plugin
implementation to sort imports alphabetically.

### Additional requirements

*   Don't write shell scripts for anything except very, very simple scripts. Use
    Python instead. Why?
    *   Re-usability from other factory software. This is the big one.
    *   Consistent command-line argument handling with `argparse`.
    *   Readability/maintainability. Yes, this is something of a matter of
        opinion: you can write relatively readable/maintainable shell scripts
        (just as you can write *un*readable/*un*maintainable Python). But see
        the
        [Google3 Shell Style Guide](https://www.corp.google.com/eng/doc/shell.xml?showone=When_to_use_Shell#When_to_use_Shell)
        for a good discussion of the issues here.
    *   **Exception**: your script needs to be able to run in an environment
        without python, e.g. initramfs.
*   Write unit tests if possible.
    *   We encourage using [mock](https://pypi.python.org/pypi/mock) module now.
        You should prevent to use
        [mox](https://code.google.com/p/pymox/wiki/MoxDocumentation) and
        [mox3](https://pypi.org/project/mox3/) modules.
*   Command-line processing
    *   Always use `argparse` for anything with a `Main()` method. Even if you
        have no command-line arguments, at least this will display a help
        screen. And trust me, you will add command-line arguments some day
        anyway :)
    *   Feel free to have single-character shortcuts, but always add a "long"
        form.
    *   Use dashes, not underscores, in command-line arguments
        (`--shopfloor-url` rather than `--shopfloor_url`). This is consistent
        with the vast majority of UNIX programs out there.
    *   For "negative" Boolean arguments, use `--no-*` and
        `action='store_false'`, e.g.

```
  parser.add_argument('--no-upload', action='store_false', dest='upload')
```

You then test it with:

```
  if args.upload:
    ... do some stuff ...
```

This is a lot more intuitive than testing negative conditions (`if not
args.no_upload`).

## Javascript/HTML/CSS

Follow the [Chromium OS Web
Development](https://chromium.googlesource.com/chromium/src/+/HEAD/styleguide/web/web.md)
style guide.

## Dealing with inconsistencies

Unfortunately, a lot of code was written either before we had real coding
standards, or written according to autotest coding standards and then moved
away. Such is life. Please use the official conventions when writing new files
(or possibly when editing in an existing file), but you can continue to use the
old conventions in existing files. Use your judgment!

## Inclusive Language
Please see [Inclusive Chromium Code](https://chromium.googlesource.com/chromium/src/+/HEAD/styleguide/inclusive_code.md).
