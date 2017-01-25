Umpire
======

Umpire stands for *Unified MES Proxy, Imaging, and Reimaging Engine*. It is
designed to be the replacement of Mini-Omaha server and Shopfloor (proxy) for
Google ChromeOS Factory Software Platform.

Umpire is created as a command-line tool. A web-based management console (with
better deployment process) is created as standalone project *Dome*.

Umpire controls what it serves by YAML config file. To make changes, you can do
`umpire edit`. After editing, the file will be temporarily saved as "staging".
You have to run the command `umpire deploy` so the new config will be activated.

Data generated (or the resources to be delivered) are stored in
`/var/db/factory/umpire/.....`.

Installation
------------
Currently the recommended approach is using Umpire inside Docker.

1. Setup a x86-64 Linux workstation with [Docker](https://www.docker.com/).
   The recommendation is [Ubuntu 16.04.1](
   http://releases.ubuntu.com/16.04/ubuntu-16.04.1-server-amd64.iso).
   During installation, please specify the system to be formatted by GPT instead
   of MBR to gain maximum disk space. Also, don't create additional partitions
   (you should only have / and /boot) since Docker saves everything in /var.

2. Extract the copy of ChromeOS factory software - probably from factory bundle
   (factory.zip) or from source. Then execute:

       setup/cros_docker.sh pull
       setup/cros_docker.sh install
       setup/cros_docker.sh umpire run

   You should see messages like

       Starting container ...
       9f37a0c111f2d77e8923ebf403f9ba571e106d584e62621857846abda051d340
       done

       *** NOTE ***
       - Host directory /docker_shared is mounted under /mnt in the container.
       - Host directory /docker_shared/umpire/$BOARD is mounted under /var/db/factory/umpire in the container.
       - Umpire service ports is mapped to the local machine.

Check if Umpire is running properly
----------------------------------
Enter docker shell and do `umpire status`.

    setup/cros_docker.sh umpire shell
     umpire status

A typical output:

    no staging config
    Mapping of bundle_id => shop floor handler path:

Deploying a factory bundle
-------------------------
Umpire by default comes with empty bundle. To feed the images (with test image,
release image, toolkit, firmware, hwid, ... etc) you have to first prepare it
with the `finalize_bundle` command. When a bundle ZIP file is available, do:

    sudo cp factory_bundle.zip /docker_shared
    setup/cros_docker.sh umpire shell
     umpire import-bundle /mnt/factory_bundle.zip
     umpire edit  # and mark the bundle in rulesets as active.
     umpire deploy

Updating resources
------------------
You have to first copy the new file into /docker_shared (which can be found as
/mnt inside docker) then notify Umpire to use them using `umpire update`
command. Example:

    # Update toolkit/hwid in bundle
    setup/cros_docker.sh umpire shell
     umpire update --from 20150702_rev3 --to 20150702_rev3_newtoolkit \
       factory_toolkit=/mnt/install_factory_toolkit.run
     umpire edit

You should see a new bundle name 20150702_rev3_newtoolkit.  Put it in ruleset
section and active it.

To update HWID:

    umpire update --from 20150702_rev3 --to 20150702_rev3_newhwid hwid=./hwid.gz

There are also resources:
 - `hwid`: HWID bundle (must be gzipped).
 - `firmware`: The chromeos-firmware script (must be gzipped).
 - `factory_toolkit`: The toolkit file (install_factory_toolkit.run).

Restarting Umpire
-----------------
The docker containers were configured to auto-restart if your machine was
rebooted unexpectedly. If you want to fully restart umpire, try
`setup/cros_docker.sh umpire stop`, `setup/cros_docker.sh umpire run`.

Changing Umpire configuration
-----------------------------
To configure additional services or to import / upgrade individual resources,
enter docker and execute `umpire edit` to get additional commands.

A sample config looks like:

    port: 8080
    rulesets:
    - bundle_id: empty_init_bundle
      note: n/a
      active: true
    services:
      http: {}
      shop_floor: {}
      rsync: {}
    bundles:
    - id: empty_init_bundle
      note: n/a
      shop_floor:
        handler: cros.factory.umpire.samus_shop_floor_handler
      resources:
        complete_script: none##00000000
      device_factory_toolkit: none##00000000
      efi_partition: none##00000000
      firmware: none##00000000
      hwid: none##00000000
      netboot_kernel: none##00000000
      oem_partition: none##00000000
      rootfs_release: none##00000000
      rootfs_test: none##00000000
      server_factory_toolkit: none##00000000
      stateful_partition: none##00000000

Currently we encourage using Dome management console instead.

Rule-based Update
-----------------
The most important advantage of using Umpire server is supporting of "rule-based
update". For example:

    - bundle_id: 20140909_proto0_smt_update
      note: SMT test list should be OK
      active: true
      enable_update:
        device_factory_toolkit: [~, ~]
        rootfs_release: [GRT, SMT]
        rootfs_test: [GRT, SMT]
        firmware_ec: [GRT, SMT]
        firmware_bios: [GRT, SMT]

Troubleshooting
---------------
There are two places for logs of Umpire.

1. Services hosted by Umpire, especially shopfloor proxy. The logs are
   accessible outside Docker. Find them in `/docker_shared/umpire/$BOARD/log`.

   For example, lighttpd logs are in:

       cd /docker_shared/umpire/$BOARD/log
       less httpd_access.log
       less httpd_error.log

2. Umpire itself. Logs are handled by docker.

       docker logs umpire_$BOARD
