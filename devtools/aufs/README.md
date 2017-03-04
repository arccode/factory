Scripts in this directory helps you working on private overlay more easily.

# Why AUFS
aufs is a kind of unionfs, which allows you to union (or merge) multiple
directories as one directory.  For Chromium OS Factory Software Platform, we
need to union files in factory repo (chromiumos/platform/factory) with files in
board overlay.  When we are developing codes in board overlay, files in factory
repo still stay in factory repo.  This makes development a little harder, for
example, you need to go back to factory repo to read the definition of an
utility function.  Or you need to figure out how to setup your auto-complete
plugin such that both files in factory repo and board overlay can be found.

With aufs, we create a **working directory** (`workspace`) for you, that both
files from factory repo and board overlay exists in this directory.  There are
also some utilities help you manage your modifications.

# File System Structure
The `workspace` is the union of three directories:
* temp directory (readwrite)
* board overlay (readonly)
* factory repo (readonly)

When you access a file, aufs first look into temp directory, then board
overlay, and finally factory repo.  Since board overlay and factory repo are
both readonly, when you modify a file, the file is copied to temp directory,
and your modification is saved in that copy.  On the other hand, if you want to
delete a file, a **whiteout marker** is created in temp directory with the file
name: `.wh.<deleted-filename>`.  For example, if you deleted `py/README.md`,
`py/.wh.README.md` will be created under temp directory.

# Utilities
## `devtools/aufs/enter.sh`
Usage: `[WORKING_DIR=...] [BOARD=...] [OVERLAY_DIR=...] enter.sh`

This will create a temp directory under `/tmp` and mount the aufs under
`~/workspace`.
* `WORKING_DIR`: specify the working directory (default: `~/workspace`)
* `OVERLAY_DIR`: specify the board overlay directory, for example:
    `~/trunk/src/privte-overlays/overlay-samus-private/chromeos-base/chromeos-factory-board/files`.
    If `OVERLAY_DIR` is not specified, `BOARD` will be used to determine the
    board overlay directory.
* `BOARD`: specify the board name to find `OVERLAY_DIR`.

## `devtools/aufs/status.sh`
Usage: `[WORKING_DIR=...] status.sh`

### Sample output
```
Modified files:
MF Makefile
A  new_file
DO py/test/test_lists/main.py
```

* `M`: this file is modified
* `A`: this file is a new file
* `D`: this file is deleted

* `F`: this file belongs to factory repo
* `O`: this file belongs to board overlay

## `devtools/aufs/diff.sh`
Usage: `[WORKING_DIR=...] diff.sh [file1 file2 ...]`

Similar to `git diff` command, this command shows changes that haven't been
sync to factory repo or board overlay.  By providing a list of files to
restrict the script only showing changes of those files.

## `devtools/aufs/sync.sh [-i|--interactive]`
Usage: `[WORKING_DIR=...] sync.sh [file1 file2 ...]`

Sync changed files to factory repo and board overlay.  Changes of existing
files (delete / modify) will be applied to files on factory repo or board
overlay.  For new files, they will be moved to board overlay.  If `interactive`
is set, a question will be prompt for each files let you decide which directory
this file should go to.

By providing a list of files, the script is restricted only syncing those files.

## `devtools/aufs/revert.sh`
Usage: `[WORKING_DIR=...] revert.sh [file1 file2 ...]`

Discard unstaged changes.  By providing a list of files, the script is
restricted only reverting those files.

## `devtools/aufs/leave.sh`
Usage: `[WORKING_DIR=...] leave.sh`

Try to unmount working directory and clean up temp directory.  If there are
unstaged files, this script will abort, working directory will not be unmounted.

# References
1. http://aufs.sourceforge.net/aufs.html
2. http://www.thegeekstuff.com/2013/05/linux-aufs/
