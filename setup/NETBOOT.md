# Chromebook Netboot Setup Guide

## What is Netboot?
**Netboot firmware** is a special firmware that instead of loading kernel from
storage, it downloads a light weight kernel (vmlinuz) from TFTP server.  And the
kernel will download ChromeOS images from [factory server](FACTORY_SERVER.md).
This is helpful when you need to re-flash ChromeOS images frequently.  Also,
this can be used in some early phase of projects (e.g. Proto builds), when
images might be changed during the build, so you don't want to pre-flash it by
copy machine.

## Prerequisition
* A Linux machine, which will be running TFTP and factory server
* An USB Ethernet dongle for DUT
* Connect DUT and Linux machine by ethernet,

  - Assume that the ethernet device on Linux machine is `eth2`
  - Assume that `eth2` is set up `192.168.200.1/24`

* Assume that the board we are going to use is `reef`
* Assume that the Linux machine is running Ubuntu (otherwise the network
    config files might need to be changed according to your Linux distribution).

## Initial Setup
Decide a folder to put TFTP files, for example, `/var/tftp`

```
BOARD=reef
sudo mkdir /var/tftp
sudo chown "${USER}" /var/tftp
mkdir -p "/var/tftp/chrome-bot/${BOARD}"
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

In the tftp-root, create sub folder under `chrome-bot` using the board name.
For example, `reef` board should be `/var/tftp/chrome-bot/reef/`.

Copy the netboot kernel into tftp board folder with name `vmlinuz`.

If you are setting up with a factory zip, the netboot kernel is in path
`factory_shim/netboot/vmlinuz`. So you have to copy it into tftp board folder
manually. For example:
```
cp factory_shim/netboot/vmlinuz /var/tftp/chrome-bot/reef/vmlinuz
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


If you want to build the netboot kernel from source, do this inside chroot:

```
cd ~/trunk/src/scripts
./build_images --board "${BOARD}"
./make_netboot.sh --board "${BOARD}"
```

And find the netboot kernel in
`../build/images/${BOARD}/latest/netboot/vmlinuz`.

The location of factory server can be specified in
`omahaserver_${BOARD}.conf` in to level of tftp, with its content set to what
you'll set in `CHROME_AUSERVER`. For example, in
`/var/tftp/omahaserver_reef.conf`:

```
http://192.168.200.1:8080/update
```

## Start DHCP & TFTP server

```
sudo dnsmasq -d -C /var/tftp/dnsmasq.conf
```

## Put Device Into Netboot Mode
Find firmware blob `image.net.bin` (which should be available in both
factory.zip and firmware archive, or you can build it locally).

```
flashrom -p host -w image.net.bin
```

## Debugging
Create an additional `cmdline` in TFTP board folder to override default kernel
boot options.  For example, in `/var/tftp/chrome-bot/reef/cmdline`:

```
lsm.module_locking=0 cros_netboot_ramfs cros_factory_install cros_secure
cros_netboot tftpserverip=192.168.200.2 console=ttyS2,115200n8 loglevel=7
earlyprintk cros_debug
```

**Note all optional must be in one line.  No newline is allowed.**

The `console` parameter might be different from board to board, if you are not
sure which should be used, please refer to "Care & Feeding" document for your
project.

## Prepare Images
You should download the recovery image, test image and factory.zip from
[CPFE](https://www.google.com/chromeos/partner/fe/#home) in following steps,

- Click Image Files on the left
- Select board (e.g. `reef`)
- Select Image type

    - `RECOVERY_IMAGE` for recovery image (signed)
    - `TEST_IMAGE_ARCHIVE` for test image
    - `FACTORY_IMAGE_ARCHIVE` for factory.zip

As we mentioned above, you can extract netboot firmware and vmlinuz from
factory.zip.  Or, if you'd like to use a specific version of firmware, you can
download it by selecting `FIRMWARE_IMAGE_ARCHIVE` in above steps.

## Deploy to Factory Server
You have to first setup a [Factory Server](FACTORY_SERVER.md) and create a
project. When ready, login to the [Dome](../py/dome/README.md) web interface,
select your project and upload the images for deployment.

To do that, you can create a complete [Bundle](BUNDLE.md), or deploy only files
you need to testing and development.

## Setting GBB Flags
When the device boots from vmlinuz, vmlinuz will connect to factory server and
download images from the server.  `chromeos-firmwareupdate` will be extracted
from recovery image, which will be used to install the real firmware.
`chromeos-firmwareupdate` will preserve the GBB flag from netboot firmware.
Therefore, you might need to change GBB flag of netboot firmware.

If you are setting up with a factory zip, the netboot image is in path
`factory_shim/netboot/image.net.bin`. You can change GBB flag by `futility`.
For example,

```
futility gbb -s --flags 0x1239 factory_shim/netboot/image.net.bin
```

If you are setting up with a factory bundle, the netboot image is in path
`netboot/image.net.bin`. You can change GBB flag by `futility`.
For example,

```
futility gbb -s --flags 0x1239 netboot/image.net.bin
```
