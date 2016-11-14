# VSWR Station Usage Guide

## Background

SWR (Standing Wave Ratio) is the ratio of the amplitude of a partial standing
wave at an antinode (maximum) to the amplitude at an adjacent node (minimum).
SWR is usually defined as a voltage ratio called the VSWR, but it is also
possible to define the SWR in terms of current, resulting in the ISWR, which has
the same numerical value. The power standing wave ratio (PSWR) is defined as the
square of the VSWR.

## Why do we need VSWR?

A problem with transmission lines is that impedance mismatches in the cable tend
to reflect the radio waves back to the source, preventing the power from
reaching the destination. SWR measures the relative size of these reflections.
An ideal transmission line would have an SWR of 1:1, with all the power reaching
the destination and none of the power reflected back. An infinite SWR represents
complete reflection, with all the power reflected back down the cable.

This test measures VSWR value using an Agilent E5071C Network Analyzer (ENA).

## Station Setup Guide

### Set Up the VSWR ENA {#set-up-the-vswr-ena}

1. Set the ENA's IP
   - Under Windows XP, Control Panel > Network Connection
   - Set it to `192.168.1.55/255.255.255.0`
2. Enable the Telnet server on the ENA
   - System > Misc Setup > Network Setup > Telnet Server = ON

### Set Up the Chrome Host {#set-up-the-chrome-host}

1. Install the Chrome OS test image into the host machine. If unclear on how to
   do this, refer to [How to reimage the host?](#how-to-reimage-the-host) below.
2. Switch to VT2 by pressing `Ctrl+Alt+F2`. Log in to the Chrome OS with
   `root / test0000`.
3. Download factory toolkit, copy it to the host, and install. Example commands:
   ```shell
   # on your computer, using scp to transfer the file
   # (you can also use a USB stick to transfer the file)
   scp install_factory_toolkit.run root@${TESTING_HOST_IP}:/tmp

   # on the testing host VT2
   cd /tmp && ./install_factory_toolkit.run
   ```
4. Reboot the host, and select VSWR test list.

### How to Reimage the Host? {#how-to-reimage-the-host}

1. Download the compressed test image file from
   [CPFE](https://www.google.com/chromeos/partner/fe/#home)
2. Decompress the file. Suppose you're working on a board named `foo`, and you
   were using version `RXX-xyzw.p.q`.
   ```shell
   tar xJvf ChromeOS-test-RXX-xyzw.p.q-foo.tar.xz
   ```
3. Write the image file into a USB stick by the following command:
   ```shell
   dd if=ChromeOS-test-RXX-xyzw.p.q-foo.bin of=/dev/sdx bs=16M
   ```
   Change `/dev/sdx` to your USB stick path.
4. Plug the USB stick into the testing host.
5. On the host, make sure it's in [developer mode](https://goo.gl/J7YjwW), and
   press `Ctrl+u` at the boot screen
6. Wait for it to boot, when finished, press `Ctrl+Alt+F2` to enter VT2. Type:
   ```shell
   chromeos-install --yes && sync && reboot
   ```
