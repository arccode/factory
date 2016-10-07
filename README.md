Google Chrome OS Factory Software Platform
==========================================
This repository contains tools and utilities used for manufacturing solution.

The layout of `/usr/local/factory`, as installed on devices' stateful
partitions, is as follows.  Most of these files are installed from
this repository, and follow this repository's directory structure.

 - `bin/`: Symbolic links to executable scripts and Python modules.
 - `build/`: Folder to contain build output artifacts.
 - `doc/`: Document templates and resources.
 - `go/`: Programs written in Go language.
 - `init/`: Initialization of factory environment for Chrome OS.
 - `misc/`: Miscellaneous resources used outside of Goofy
 - `proto/`: Proto-buf schema definition.
 - `setup/`: Scripts and programs for partner to setup the environment.
 - `sh/`: Shell scripts.
 - `py_pkg/`: Symbolic link to enable importing Python packages

 - `py/`: Python source code in the cros.factory module and sub-modules.
   See `py/README.md` for more information.

 - `board/`: Board-specific files (optional and only provided by board overlays,
    not this repository.in board overlay):
    - `board_setup_factory.sh`: A script to add board-specific arguments when
      starting the Goofy (the factory test harness).
    - Other files needed by board-specific tests.

Within the build root (`/build/$BOARD`), `/usr/local/factory/bundle` is a
"pseudo-directory" for the factory bundle: it is masked with
`INSTALL_MASK` so it is not actually installed onto devices, but any
files in this directory will be included in factory bundles built by
Buildbot.  For example, the shopfloor and mini-Omaha servers are
placed into this directory.

Within board overlays, the `chromeos-base/chromeos-factory-board`
package may overlay files into this directory structure.

For instance, a board overlay may install:

 - A board-specific test into `/usr/local/factory/py/test/pytests`.

 - `/usr/local/factory/bundle/README` to include a README in the
   factory bundle.

 - Any arbitrary board-specific file (e.g., a proprietary tool
   licensed only for use on a particular board) into
   `/usr/local/factory/board`.

 - `/usr/local/factory/board/board_setup_{factory,x}.sh` to customize
   Goofy or X arguments.
