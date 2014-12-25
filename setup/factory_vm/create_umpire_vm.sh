#!/bin/sh
# Copyright 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

# This is a helper script to be create libvirt VM for factory server
# testing.
#
# Usage:
#   Create Umpire VM:
#     ./uvt_umpire.sh
#   Remove previous Umpire VM and create a new one:
#     ./uvt_umpire.sh  -f
#   Get Umpire IP address:
#     uvt-kvm ip umpire
#   Connect to Umpire VM:
#     uvt-kvm ssh umpire --insecure
#   Change host DHCP range:
#     virsh net-edit default
#

# uvtools/libvirt domain
VM_DOMAIN="umpire"
# debian/ubuntu distribution
VM_ARCH="amd64"
VM_RELEASE="trusty"
# memory size in MiB
VM_MEMORY=2048
# number of cpus
VM_CPU=1
# disk size in GiB
VM_DISK=32
# ssh public key file name, place in same directory as this script
VM_PUBLIC_KEY=testing_rsa.pub
# extra packages to install
VM_PACKAGES="linux-image-generic,python-yaml,python-netifaces,python-pexpect,"\
"python-numpy,python-twisted,python-twisted-web,python-protobuf,lighttpd,"\
"python-flup,unzip,parallel,pbzip2,pigz,binutils,sharutils,rsync,aptitude,"\
"screen,vim,psmisc,dbus,ssh,htop"

# host dependencies
HOST_REQUIRED_PACKAGES="uvtool-libvirt qemu-kvm"

# get script base directory
BASE_DIR=$(dirname $(readlink -f $0))


# check and install debian package
may_install_system_dependencies() {
  local pkg_name="$1"
  echo "$(date): Check package $pkg_name"
  if ! dpkg -s "$pkg_name" 2>/dev/null |
      grep -q "Status: install ok installed"; then
    echo "$(date): Install package $pkg_name"
    sudo apt-get install $pkg_name
  fi
}


# sync uvtool distro
may_sync_uvtool_distro() {
  local not_found=1
  uvt-simplestreams-libvirt query arch="$VM_ARCH" release="$VM_RELEASE" |
    grep -q "release=$VM_RELEASE" && not_found=0
  if [ "$not_found" != "0" ]; then
    echo "$(date): Synchronize distro $VM_RELEASE"
    uvt-simplestreams-libvirt sync arch="$VM_ARCH" release="$VM_RELEASE"
    uvt-simplestreams-libvirt query
    echo "$(date): Synchronized"
  fi
}


# install host dependencies
for pkg_name in $HOST_REQUIRED_PACKAGES; do
  may_install_system_dependencies $pkg_name
done

# add current user to libvirtd group
if ! grep libvirtd: /etc/group | grep -q $(id -un); then
  echo -n "$(date): Add $(id -un) to group libvirtd"
  sudo usermod -G libvirtd $(id -un)
fi

# log out and back in if needed
if ! groups | grep -q libvirtd; then
  # logout current session and login again
  echo "**************************************************"
  echo "* After changing user group, you will need to    *"
  echo "* log out and back in for the group membership   *"
  echo "* to take effect.                                *"
  echo "**************************************************"
  read -p "Press enter to continue ..."
  gnome-session-quit --force > /dev/null 2>&1
  if [ -f /etc/init/lightdm ]; then
    if initctl status lightdm | grep -q running; then
      sudo initctl restart lightdm
    fi
  fi
  if [ -f /etc/init/gdm ]; then
    if initctl status gdm | grep -q running; then
      sudo initctl restart gdm
    fi
  fi
  exit
else
  groups | grep --color=always libvirtd
fi


exist=$(uvt-kvm list | grep $VM_DOMAIN 2>/dev/null)
if [ "$1" = "-f" -o "$1" = "--force" -o "$exist" = "" ]; then
  if [ "$exist" = "$VM_DOMAIN" ]; then
    echo "Removing existing domain $VM_DOMAIN"
    uvt-kvm destroy "$VM_DOMAIN"
  fi
  may_sync_uvtool_distro
  echo "$(date): Creating domain $VM_DOMAIN"
  uvt-kvm create "$VM_DOMAIN" release="$VM_RELEASE" \
      --memory "$VM_MEMORY" \
      --cpu "$VM_CPU" \
      --disk "$VM_DISK" \
      --ssh-public-key-file "$BASE_DIR/$VM_PUBLIC_KEY" \
      --packages "$VM_PACKAGES"
  echo "$(date): Waiting for $VM_DOMAIN installation to complete"
  uvt-kvm wait "$VM_DOMAIN" --insecure
  echo "$(date): Done!"
fi
