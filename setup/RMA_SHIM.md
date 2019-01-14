# Chrome OS RMA shim

[TOC]

## What is an RMA shim?

An RMA shim is a
[factory install shim](https://chromium.googlesource.com/chromiumos/platform/factory_installer)
with all the [bundle](setup/BUNDLE.md) components stored in the shim. We can
install everything to a device using an RMA shim without network. It is called
"RMA shim" because it is widely used in RMA (Return Merchandise Authorization)
flow.

## Create an RMA shim

To create an RMA shim image from a [bundle](setup/BUNDLE.md), use `rma-create`
subcommand in `image_tool`:

    ./setup/image_tool rma-create \
      --board=BOARD \
      --factory_shim=path/to/factory_install_shim.bin \
      --test_image=path/to/chromiumos_test_image.bin \
      --toolkit=path/to/install_factory_toolkit.run \
      --release_image=path/to/chromiumos_image.bin \
      --hwid=path/to/hwid_bundle.sh \
      --output=rma_image.bin

The command can be simplified if all the components are put in their respective
bundle directories (release_image/, test_image/, etc.):

    ./setup/image_tool rma-create --board=BOARD --output=rma_image.bin

## Use an RMA shim

Flash the `rma_image.bin` to a USB stick, boot it with developer switch
enabled in recovery mode (see following steps), and then the device will boot
from the RMA shim.

#### Boot from RMA shim (clamshells / convertibles)
  1. Press `ESC + F3(REFRESH) + POWER` to enter recovery mode
  2. Press `CTRL + D` to turn on developer switch
  3. Press `ENTER` to confirm
  4. Press `ESC + F3(REFRESH) + POWER` to enter recovery mode again (no need to
     wait for wiping)
  5. Insert and boot from USB stick with `rma_image.bin`

#### Boot from RMA shim (tablets / detachables)
  1. Press `POWER + VOL_UP + VOL_DOWN` for at least 10 seconds, and release them
     to enter recovery mode
  2. Press `VOL_UP + VOL_DOWN` to show recovery menu
  3. Press `VOL_UP` or `VOL_DOWN` to move the cursor to "Confirm Disabling OS
     Verification", and press `POWER` to select it
  4. Press `POWER + VOL_UP + VOL_DOWN` for at least 10 seconds, and release them
     to enter recovery mode again (no need to wait for wiping)
  5. Insert and boot from USB stick with `rma_image.bin`

The RMA shim has a menu that allows the user to select an action to perform,
which is described in
[Factory Installer README](https://chromium.googlesource.com/chromiumos/platform/factory_installer/#factory-shim-menu).
Moreover, if the RMA shim is created using `image_tool rma-create` command, the
tool adds a flag `RMA_AUTORUN=1` in `lsb-factory` file, which sets the default
action of the menu depending on the cr50 version and hardware write protect
status.
  1. If hardware write protect is enabled, and cr50 version is older than the
     cr50 image in the shim, set the default action to **(U) Update cr50**.
     After cr50 is updated, the device will reboot. The user should enter
     recovery mode and boot to shim again.
  2. If hardware write protect is enabled, and cr50 version is not older than
     the cr50 image in the shim, set the default action to **(E) Reset Cr50**,
     also known as RSU (RMA Server Unlock) to disable hardware write protect
     and enter factory mode. After RMA reset, the device will reboot. The user
     should enter recovery mode and boot to shim again.
  3. If hardware write protect is disabled, set the default action to
     **(I) install** to install payloads from USB. If hardware write protect is
     disabled by disconnecting the battery instead of doing RSU, the install
     script will also enable factory mode at the end of installation.

You can stop the default action and return to shim menu by pressing any key
within 3 seconds when the console prompts "press any key to show menu instead".

After the installation, the device will boot into the test image with factory
toolkit.
