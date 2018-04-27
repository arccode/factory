# Resources for build system

The Chromium OS Factory Software build system relies on "resources" to build
packages and images. In `chromiumos-overlay/eclass/cros-factory.eclass`,
you can create individual resource files by function
`factory_create_resource`, and the files will be unpacked by ebuild packages for
installation.

To help sharing resources and simplify customization, the `resources` folder is
introduced. You can declare a new resource here by creating a `*.rsrc` file.

## Declaring a resource
The base name of `.rsrc` (before any extensions) file is the name of output
resource. For example. You can have multiple `rsrc` declaration files joined
together to create one single resource file. For example, `target.rsrc`,
`target.1.rsrc`, `target.something.rsrc` will be concatenated to build
`target.tar` resource file.

The syntax for for `rsrc` is simple. Lines started with `#` or empty lines are
ignored. Each valid line should be in:

    [?]SOURCE[:DEST]

- `SOURCE` refers to what file (or directory) to add.
- `DEST` is optional. If given, it will be the path inside resource.
- `?` can be prefixed to indicate this is an optional resource.

If `SOURCE` is an absolute path, we will find it in the `$SYSROOT` (`--sysroot`).
If `SOURCE` is relative, we will search for it in `$BOARD_FILES_DIR/resources`
(`--board_resources`) first, then public resource `resources/` (`--resources`).
If `SOURCE` exists in both board resource folder and public resource folder,
**both will be included**.

The resources will be created by [Makefile](../Makefile) calling
[devtools/mk/create_resources.py](../devtools/mk/create_resources.py)
when building `chromeos-base/factory`.

## Installer resource
The `installer` is a resource to be installed for
`chromeos-base/factory_installer` package, which is shared by factory shim
(`fatory_install` image, or known as reset shim) and netboot image. The files
will be installed into `/usr` on factory shim root file system.
`/usr/sbin/factory-*` will be also installed into netboot image.

One special file you may want to add is `factory_install_board.sh`, which will
be loaded by `factory_install.sh` to override `BOARD` settings and functions.

To do this, simply add the file in private overlay as:
`chromeos-base/factory-board/files/resources/factory_install_board.sh`.

(The file is already described in `installer.rsrc` as optional resource file.)

# Toolkit resources
If you want to put files only for toolkit (i.e., par won't have it), put it
under `resources/` and create a `resources/toolkit-XXX.rsrc` description file
to specify where to add the files.

# PAR resources
The `factory.par` may include additional resources. Create a resource as
`resouces/par-XXX.rsrc` for it.

# Generic resources
If you name the resource definition (`*.rsrc`) file with `resource` or `factory`
as prefix then all build generic targets (`toolkit`, `par`, but not `installer`)
will have it. For example `resource-XXX.rsrc` or `factory-XXX.rsrc`.

# Bundle resources
If there is something that should only appear in bundle (or the "factory ZIP")
then it should be described in `bundle-XXX.rsrc` file.
