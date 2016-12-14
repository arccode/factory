Google Chromium OS Factory Software Platform
============================================

Overview
--------
This repository contains tools and utilities used for manufacturing solution.
The Chromium OS reference factory software provides a sample factory install and
test flow for manufacturing Chrome devices. It is available as part of the
public Chromium OS repository on chromium.org. This code is meant as a starting
point, to modify and adapt to different projects.

The Chromium OS Factory Software Platform has three major components:
 * **DUT Software**: Everything runs on DUT (Device-under-test), including a
     test harness, qualification, calibration and functional test programs, and
     steps for finalization like battery cutoff or wiping.
 * **Factory Server**: The bridge between DUT and partner's shopfloor service,
     including imaging service, shopfloor proxy, and a management console.
 * **Google Backend**: The solution for sending manufacturing logs back to
     Google infrastructure.

Terminology
-----------
* Test image: the Chromium OS test image (built by `build_image test`).
* Release image: the (usually signed) release image that end user is using
    (built by `build_image base`).
* Recovery image: the (usually signed) release image with recovery installer
    so it's in install-able form (built by `build_image base;
    mod_image_for_recovery` and can be downloaded directly from ChromeOS
    Buildbots or CPFE).
* Factory shim image: a special multi-purpose image that provides:
  * Installation from USB (also known as RMA shim).
  * Installation from remote server (mini-omaha). Also known as Factory Install
      shim in this case.
  * Reset or cutoff a device after OOBE. Also known as Reset Shim in this case.
* Factory toolkit: a self-extraction package that contains a set of python
    programs, YAML/JSON configuration, and shell scripts that will install
    itself into /usr/local/factory. This is also considered as the main "factory
    test program" (built by running `emerge-$BOARD factory` or
    `make BOARD=$BOARD toolkit` inside factory repository).
* Factory Bundle: An archive containing everything: a release (recovery) image,
  test image, factory shim image, factory toolkit, and few setup programs.

Typical Factory Flow
--------------------
The basic steps are:

1. An initial/bootable version of the firmware for
   [AP](http://www.chromium.org/chromium-os/2014-firmware-summit) (and
   [EC](http://www.chromium.org/chromium-os/ec-development)) is pre-flashed
   onto the SPI-ROM (and Chromium EC chip) before system assembly.
2. After system assembly, insert the Factory Install Shim USB stick. After the
   device boots and the DEV mode screen displays, press Ctrl-U to boot from USB.
   The shim contacts a mini-Omaha server to request an install image.
   The netboot version of firmware also supports booting and installing from a
   network location using tftp, without a USB stick.
3. The factory toolkit, test image, signed release image, and AP/EC firmware are
   installed or updated. Included on disk are two full Chrome OS images: the
   test image and the shipping image.
4. The system automatically reboots using the test image and and begins
   manufacturing tests. This test suite is based on [pytest](py/pytests). The
   software supports sequencing tests, configuration, firmware and configuration
   updates, reboots, and other events in a configurable sequence.
5. Functional, Run-In, and manual tests run as configured. Upon completion,
   results are displayed on the screen. Results are also available as an
   electronic pass/fail record with detailed logs for uploading to the shopfloor
   server.
6. The test image and test code are automatically erased, leaving the release
   image as bootable in the "finalization" step.
7. On failure, the system continues running subsequent tests and reports
   failures on completion. Alternatively you can configure it to halt on failure
   at specific break points. For details, see the Options class in
   src/platform/factory/py/test/factory.py and generic test lists under
   src/platform/factory/py/test/test_lists/* .
8. The factory image and test image can be combined into an SSD image and imaged
   onto the internal drive before assembly. The first time the device boots, the
   sequence starts at step 4 above, using the factory test image.

Building Factory Toolkit
------------------------
Under chroot, after [setting up
board](http://dev.chromium.org/chromium-os/developer-guide), you have two ways
to get factory toolkit.

1. Using emerge. Simply run `emerge-$BOARD factory` and find it in
   `/build/$BOARD/usr/local/factory/bundle/toolkit/install_factory_toolkit.run`

2. Build manually. In factory repo, run `make BOARD=$BOARD toolkit` and find
   it in `build/install_factory_toolkit.run`.

If you encounter build problems, try to update chroot and rebuild necessary
dependencies by running `build_packages` and then try again.

The toolkit can be installed into a Chromium OS test image, by either running
that locally on a DUT, or apply to a test image directly as blow:

    ./install_factory_toolkit.run PATH_TO/chromiumos_test_image.bin

Building Test Image
-------------------
Under chroot, after [setting up
board](http://dev.chromium.org/chromium-os/developer-guide), you can get the
factory shim by running following commands in `trunk/src/scripts`:

    build_packages
    build_image test

After image is built, you can flash it into an USB stick (assume your USB
appears as `sdX`):

    # outside chroot
    cros flash usb:// chromiumos_test_shim.bin

    # outside chroot
    sudo dd bs=4M if=/path/to/image/chromiumos_test_shim.bin of=/dev/sdX \
            iflag=fullblock oflag=dsync

Building Factory (Install) Shim
-------------------------------
Under chroot, after [setting up
board](http://dev.chromium.org/chromium-os/developer-guide), you can get the
factory shim by running following commands in `trunk/src/scripts`:

    build_packages
    build_image factory_install

There are few options that you may want to change. Run
`setup/edit_lsb_factory.sh` to get more information.

After image is built, you can flash it into an USB stick (assume your USB
appears as `sdX`):

    # outside chroot
    cros flash usb:// chromiumos_install_shim.bin

    # outside chroot
    sudo dd bs=4M if=/path/to/image/factory_install_shim.bin of=/dev/sdX \
            iflag=fullblock oflag=dsync

On boot, the factory shim displays a download status and downloads the image
from the server. On completion, the shim reboots. If you are using legacy
firmware (not Chrome OS firmware), you might need to remove the SD card to allow
booting the newly-installed image.

After the image starts downloading and the status message turns green, you can
remove the SD card—it is not needed after that point.

Building an SSD image
---------------------
To pre-image the machines rather than image them over the network, you can
generate the disk image from a factory test image and a release image.

A generic factory package can be built from a release image and a factory image:

    ./make_factory_package.sh --diskimg=ssd_image.bin \
      --test=/path/to/chromiumos_test_image.bin \
      --factory_toolkit=/path/to/install_factory_toolkit.run \
      --release=/path/to/chromiumos_image.bin \
      --hwid=/path/to/hwid_bundle.sh

You can image directly to a device, or to a .bin file. Available options are:

 * `--diskimg=XX` specifies the destination device or file
 * `--sectors=XX` specifies the number of sectors in the bin file
 * `--preserve` prevents wiping of the unused space for faster imaging

Booting your (factory) test image via USB
-----------------------------------------
For development and local testing, it is possible to boot the factory test image
from a USB memory stick rather than using a network install. The following steps
are optional:

1. Copy the test image to USB storage.
2. On your device, switch to developer mode. For most recent devices, this is
   done by pressing Esc-F3-Power (F3 is the refresh key on top row) then press
   Ctrl-D when the screen said that your need to insert a recovery USB stick,
   and press ENTER when the screen asked you to do.
3. After system reboot, enter VT2 by pressing Ctrl-Alt-F2 (F2 is the right-arrow
   key on top row).
3. Log in as root with password `test0000` if required.
4. Run the following command: `sudo chromeos-firmwareupdate --mode=todev`
5. Insert the USB memory stick and press Ctrl-U at the dev mode warning
   screen. You can also enter VT2 and install the image to SSD using the
   `chromeos-install` command.

Preparing a factory package set
-------------------------------
By default, a factory installation places the factory test image in the first
slot of Chrome OS image partitions ([#2 and #3](http://www.chromium.org/chromium-os/chromiumos-design-docs/disk-format#TOC-Drive-partitions)),
and the release image in the second slot (#4 and #5).

You can build a generic factory package from a release image and a factory image
as follows:

    # (cros-chroot)
    ~/trunk/src/scripts/make_factory_package.sh \
      --test=/path/to/chromiumos_test_image.bin \
      --factory_toolkit=path/to/install_factory_toolkit.run \
      --release=/path/to/chromiumos_image.bin \
      --hwid=/path/to/hwid_bundle.sh

Modifying factory test image or adding test cases
-------------------------------------------------
The factory test image runs the series of [pytests](py/pytests) located at
`src/platform/factory/py/test/pytests/` (installed in
`/usr/local/factory/py/test/pytests/` on the DUT). The sequence of pytest cases
are determined by `test_lists` files under
`/usr/local/factory/py/test/test_lists/`. Status is logged to
`/var/log/factory.log` and more details can be found under `/var/factory/*`.

After modifying the source code, you can run the following commands to push
files to the DUT. The host machine and DUT must be on the same subnet.

1. Enter chroot.
2. Update factory source code on DUT:

    ./bin/goofy_remote DUT_IP_ADDRESS

For more information on adding test cases, build the **Chromium OS Factory SDK
documentation**:

1. Enter chroot.
2. Build the SDK documentation

    make doc

3. Open the following file in a browser window:

    build/doc/index.html

Developer Notes
---------------
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

Within board overlays, the `chromeos-base/factory-board` or
`chromeos-base/chromeos-factory-board` package may overlay files into this
directory structure.

For instance, a board overlay may install:

 - A board-specific test into `/usr/local/factory/py/test/pytests`.

 - `/usr/local/factory/bundle/README` to include a README in the
   factory bundle.

 - Any arbitrary board-specific file (e.g., a proprietary tool
   licensed only for use on a particular board) into
   `/usr/local/factory/board`.

 - `/usr/local/factory/board/board_setup_{factory,x}.sh` to customize
   Goofy or X arguments.
