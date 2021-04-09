# Chromebook Netboot Setup Guide

## What is Netboot?
**Netboot firmware** is a special firmware that instead of loading kernel from
storage, it downloads a light weight kernel (vmlinuz) from TFTP server.  And the
kernel will download ChromeOS images from [factory server](FACTORY_SERVER.md).
This is helpful when you need to re-flash ChromeOS images frequently.  Also,
this can be used in some early phase of projects (e.g. Proto builds), when
images might be changed during the build, so you don't want to pre-flash it by
copy machine.

## Overview
The netboot imaging flow contains the following steps:

1. Enter netboot mode with netboot or dev firmware.
2. Download `vmlinuz` kernel from TFTP server in netboot mode.
3. Download images (with [cros_payload](../sh/cros_payload.sh)) from the factory
   server in `vmlinuz` kernel.

Therefore, you need to setup the following components to do a netboot imaging:

* Flash the devices with netboot or dev firmware to enter netboot mode.
* Setup a TFTP server to deploy netboot kernel.
* Setup a factory server with image resources.
* Specify netboot settings (e.g., factory server IP).

Details of each component can be found in corresponding sections in this
document.

## Prerequisition
* A Linux machine, which will be running TFTP and factory server
* An USB Ethernet dongle for DUT
* Connect DUT and Linux machine by ethernet,

  - Assume that the ethernet device on Linux machine is `eth2`
  - Assume that `eth2` is set up `192.168.200.1/24`

* Assume that the board we are going to use is `zork`, and the model name is
    `morphius`
* Assume that the Linux machine is running Ubuntu (otherwise the network
    config files might need to be changed according to your Linux distribution).

## Put Device Into Netboot Mode
Find firmware blob `image-${MODEL}.net.bin` (which should be available in
firmware archive, or you can build it locally).

```
flashrom -p host -w image-${MODEL}.net.bin
```

Alternatively, you can also install **dev firmware** (`image-${MODEL}.dev.bin`)
to the device, and press `Ctrl + N` in the developer screen to enter netboot
mode. This effectively runs the same netboot code as full netboot firmware.

## Setup TFTP server

### Setup TFTP server with Dome

If your network infrastructure already has a DHCP server, you can setup the TFTP
server from Dome UI with the following steps:

1. Upload the `vmlinuz` kernel (and `netboot_cmdline` file if needed) to Umpire.
2. Select the ☆ button (use this bundle's netboot resource) at the bundle.
3. Enable **TFTP server** in Dome config page.

By default this will create a TFTP folder at `/cros_docker/tftp/`, and the
netboot kernel and cmdline files will be copied to
`/cros_docker/tftp/chrome-bot/${PROJECT}/`, where `${PROJECT}` is the project
name of the Umpire instance. So if the project name on Umpire does not match the
model name, you have to override the path to the netboot kernel and cmdline
to download them from TFTP server; see
[Netboot Settings](#netboot-settings) section for more details.

### Setup TFTP server and DHCP server with `dnsmasq`
Decide a folder to put TFTP files, for example, `/var/tftp`

```
sudo mkdir /var/tftp
sudo chown "${USER}" /var/tftp
mkdir -p "/var/tftp/chrome-bot/${MODEL}"
```

Create a [`dnsmasq`](http://www.thekelleys.org.uk/dnsmasq/doc.html) setup config
in TFTP root, for example, `/var/tftp/dnsmasq.conf`, with the following
contents:

```
interface=eth2
tftp-root=/var/tftp
enable-tftp
dhcp-leasefile=/tmp/dnsmasq.leases
dhcp-range=192.168.200.50,192.168.200.150,12h
port=0
```

Assuming that you are running Ubuntu, you can setup static IP for `eth2` by
adding a file `/etc/network/interfaces.d/eth2.conf` (you can change the name
`eth2.conf` to whatever you like):

```
auto eth2
allow-hotplug eth2
iface eth2 inet static
    address 192.168.200.1
    netmask 255.255.255.0
```

Reload the configuration by running:

```
sudo ifup eth2
```

Then `ip addr show eth2` and check if it has inet address `192.168.200.1/24`
assigned.  If not, reboot Linux machine and see if that works.

Make sure you have `dnsmasq` installed on Linux machine (e.g. Ubuntu / Debian)

```
sudo apt-get install dnsmasq
```

In the tftp-root, create sub folder under `chrome-bot` using the model name.
For example, `morphius` model should be `/var/tftp/chrome-bot/morphius/`.

Copy the netboot kernel into tftp model folder with name `vmlinuz`.

If you are setting up with a factory zip, the netboot kernel is in path
`factory_shim/netboot/vmlinuz`. So you have to copy it into tftp model folder
manually. For example:
```
cp factory_shim/netboot/vmlinuz /var/tftp/chrome-bot/morphius/vmlinuz
```

If you are setting up with a factory bundle (prepared by `finalize_bundle`
command and is usually a `tar.bz2` archive), the tftp folder is already prepared
in `netboot/tftp`. So you have to copy everything to your tftp root,
or start `dnsmasq` server from there. For example:
```
cp -r netboot/tftp/* /var/tftp/
```

*** note
**Note:** Some boards might call vmlinuz as "vmlinux.bin".
***

### Start DHCP & TFTP server

```
sudo dnsmasq -d -C /var/tftp/dnsmasq.conf
```

## Prepare Images
You should download the recovery image, test image and factory.zip from
[CPFE](https://www.google.com/chromeos/partner/fe/#home) in following steps,

- Click Image Files on the left
- Select board (e.g. `zork`)
- Select Image type

    - `RECOVERY_IMAGE` for recovery image (signed)
    - `TEST_IMAGE_ARCHIVE` for test image
    - `FACTORY_IMAGE_ARCHIVE` for factory.zip

As we mentioned above, you can extract netboot firmware and vmlinuz from
factory.zip.  Or, if you'd like to use a specific version of firmware, you can
download it by selecting `FIRMWARE_IMAGE_ARCHIVE` in above steps.

### Build Netboot Kernel

If you want to build the netboot kernel from source, do this inside chroot:

```
# You can skip the `cros-workon` and `emerge` commands if you don't have
# local changes.
cros-workon-${BOARD} factory factory_installer

# Replace ${VER} with the kernel version used by your board, and you only need
# to build the kernel once. If you don't know the version number, run
# `emerge-${BOARD} -pv virtual/linux-sources`.
emerge-${BOARD} chromeos-kernel-${VER}
emerge-${BOARD} factory factory_installer

cd ~/trunk/src/scripts
./build_images --board "${BOARD}"
./make_netboot.sh --board "${BOARD}"
```

*** note
If you need to add any USE flags while building kernel, add USE flags to
environment variables.
```
USE="..." ./make_netboot.sh --board "${BOARD}"
```
***

And find the netboot kernel in
`../build/images/${BOARD}/latest/netboot/vmlinuz`.

## Deploy to Factory Server
You have to first setup a [Factory Server](FACTORY_SERVER.md) and create a
project. When ready, login to the [Dome](../py/dome/README.md) web interface,
select your project and upload the images for deployment.

To do that, you can create a complete [Bundle](BUNDLE.md), or deploy only files
you need to testing and development.

* Required resources are `test_image`, `release_image`, `toolkit`, and
    `netboot_kernel`.
* `complete`, `project_config`, `hwid`, and `firmware` are optional resources,
    but `hwid` and `firmware` are required in typical factory scenarios.

## Netboot Settings
This section introduces the settings during the netboot process and how to
customize them.

### Factory server IP
The factory server (Umpire) IP (e.g., `http://192.168.200.1:8080`) for the
netboot kernel to download the image files. To specify this, you can do one
of the following approaches:

* Append `omahaserver=http://192.168.200.1:8080` in the kernel boot options
    (`cmdline`).
* Use `--factory-server-url` argument in [netboot_firmware_settings.py](
    ../py/tools/netboot_firmware_settings.py). This will append the argument
    (`omahaserver=`) in kernel boot options (`cmdline`) for you.
* Create a `omahaserver_${BOARD}.conf` under the TFTP root (for example,
    `/var/tftp/omahaserver_zork.conf`), and set its content to the factory
    server IP (for example, `http://192.168.200.1:8080`). This will override the
    `omahaserver` settings in kernel boot options.

The default value is `CHROMEOS_AUSERVER` (typically `http://10.0.0.1:8080`).

**This is a required argument for netboot process.**

### TFTP server IP for firmware
The TFTP server IP to download the netboot kernel and kernel boot option file
(`cmdline`) from. To specify this, you can do one of the following approaches:

* Modify the siaddr field (next-server) in DHCP message.
* Use `--tftpserverip` argument in [netboot_firmware_settings.py](
    ../py/tools/netboot_firmware_settings.py). This will override the setting
    in DHCP message.

The default value is the IP address of DHCP server.

**This is a required argument if you have separate DHCP server and TFTP server.
**

### Board name
The board name of the device. This changes the path to the factory server IP
config file on TFTP server (`/var/tftp/omahaserver_${BOARD}.conf`), so you can
override the board name to connect to different factory server. To specify this,
you can do one of the following approaches:

* Append `cros_board=${BOARD}` in the kernel boot options (`cmdline`).
* Use `--board` argument in [netboot_firmware_settings.py](
    ../py/tools/netboot_firmware_settings.py). This will append the argument
    (`cros_board=`) in kernel boot options (`cmdline`) for you.

The Default value is the board name (`CHROMEOS_RELEASE_BOARD`) of the device.

### Netboot kernel boot options
The boot options (`cmdline`) for the netboot kernel. To specify this, you can do
one of the following approaches:

* Use `--kernel_arg` argument in [netboot_firmware_settings.py](
    ../py/tools/netboot_firmware_settings.py).
* Upload `netboot_cmdline` resource to the [factory server](FACTORY_SERVER.md).
    **Note that this will override all boot options specified by
    [netboot_firmware_settings.py](../py/tools/netboot_firmware_settings.py).
    **

The default value is
```
lsm.module_locking=0 cros_netboot_ramfs cros_factory_install cros_secure
cros_netboot
```

See [Debugging](#debugging) and [Skip Complete Prompt](#skip-complete-prompt)
section for more information on kernel boot options.

### TFTP server IP for netboot kernel
If you want to specify a different TFTP server IP for downloading
`omahaserver_${BOARD}.conf` in netboot kernel, you can append
`tftpserverip=${TFTP_SERVER_IP}` into the kernel boot options (`cmdline`). The
default value is the TFTP server
IP for downloading the netboot kernel.

### Path to netboot kernel
The path to the netboot kernel on TFTP server. To Specify this, you can do one
of the following approaches:

* Modify the `file` (filename) field in DHCP message.
* Use `--bootfile` argument in [netboot_firmware_settings.py](
    ../py/tools/netboot_firmware_settings.py). This overrides the setting in
    the DHCP message.

The default value is `chrome-bot/{MODEL}/vmlinuz`.

### Path to netboot kernel boot options file
The path to the netboot kernel boot options file (`cmdline`) on TFTP server.
You can specify this by `--argsfile` argument in [netboot_firmware_settings.py](
    ../py/tools/netboot_firmware_settings.py).

The default value is `chrome-bot/{MODEL}/cmdline`.

## Debugging
Create an additional `cmdline` in TFTP model folder to override default kernel
boot options.  For example, in `/var/tftp/chrome-bot/morphius/cmdline`:

```
lsm.module_locking=0 cros_netboot_ramfs cros_factory_install cros_secure
cros_netboot tftpserverip=192.168.200.2 console=ttyS2,115200n8 loglevel=7
earlyprintk cros_debug
```

**Note all optional must be in one line.  No newline is allowed.**

The `console` parameter might be different from board to board, if you are not
sure which should be used, please refer to "Care & Feeding" document for your
project.

## Skip Complete Prompt
By default, you'll see a big "OK" when the netboot completes, and you have to
press ENTER key to reboot into the factory software.

If you want to disable the prompt, you can append `nocompleteprompt` to the
kernel boot options (`cmdline`).

## Setting GBB Flags
When the device boots from vmlinuz, vmlinuz will connect to factory server and
download images from the server.  `chromeos-firmwareupdate` will be extracted
from recovery image, which will be used to install the real firmware.
`chromeos-firmwareupdate` will preserve the GBB flag from netboot firmware.
Therefore, you might need to change GBB flag of netboot firmware.

If you are setting up with a factory zip, the netboot image is in path
`factory_shim/netboot/image-${MODEL}.net.bin`. You can change GBB flag by
`futility`.
For example,

```
futility gbb -s --flags 0x1239 factory_shim/netboot/image-${MODEL}.net.bin
```

If you are setting up with a factory bundle, the netboot image is in path
`netboot/image-${MODEL}.net.bin`. You can change GBB flag by `futility`.
For example,

```
futility gbb -s --flags 0x1239 netboot/image-${MODEL}.net.bin
```
