# Chrome OS Factory Software Setup and Deployment

This folder contains tools and scripts for factory flow setup. All programs here
may need to run on few different environments:

- Inside chroot of cros_sdk
- Outside chroot but still with complete source tree
- Inside a factory bundle running on arbitrary Linux device (no source tree).

So all programs must use only the libraries in same folder or packaged into
a standalone program when deployed.

## List of available commands

### [cros_docker.sh](./cros_docker.sh)
This is the main script for [Factory Server](FACTORY_SERVER.md) deployment.

### [image_tool](../py/tools/image_tool.py)
This is an integrated program with sub commands for manipulating Chromium OS
disk images for different purposes, including:

- `bundle`: Creates a [factory bundle](BUNDLE.md) from given arguments.
- `docker`: Create a Docker image from existing Chromium OS disk image.
- `preflash`: Create a disk image for factory to pre-flash into internal storage.
- `edit_lsb`: Edit contents of 'lsb-factory' file from a factory_install image.
- `get_firmware`: Extracts firmware updater from a Chrome OS disk image.
- `rma create`: Create an RMA image for factory to boot from USB and repair device.
- `rma merge`: Merge multiple RMA images into one single large image.
- `rma show`: Show the content of an RMA image.
- `mount`: Mounts a partition from Chromium OS disk image.
- `netboot`: Access Chrome OS [netboot](NETBOOT.md) firmware (image.net.bin) settings.
- `resize`: Changes file system size from a partition on a Chromium OS disk image.

Run `image_tool help COMMAND` (replace `COMMAND` by the name of sub command) to
get more details.

### [cros_payload](../sh/cros_payload.sh)
The underlying tool for creating resources for factory server and various (RMA,
preflash) images.

### [create_hwid_bundle.sh](./create_hwid_bundle.sh)
A tool to re-create or merge HWID config files.
