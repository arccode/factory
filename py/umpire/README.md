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
       - Host directory /cros_docker is mounted under /mnt in the container.
       - Host directory /cros_docker/umpire/$BOARD is mounted under /var/db/factory/umpire in the container.
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

    sudo cp factory_bundle.zip /cros_docker
    setup/cros_docker.sh umpire shell
     umpire import-bundle /mnt/factory_bundle.zip
     umpire edit  # and mark the bundle in rulesets as active.
     umpire deploy

Updating resources
------------------
You have to first copy the new file into /cros_docker (which can be found as
/mnt inside docker) then notify Umpire to use them using `umpire update`
command. Example:

    # Update toolkit/hwid in bundle
    setup/cros_docker.sh umpire shell
     umpire update --from 20150702_rev3 --to 20150702_rev3_newtoolkit \
       toolkit=/mnt/install_factory_toolkit.run
     umpire edit

You should see a new bundle name 20150702_rev3_newtoolkit.  Put it in ruleset
section and active it.

To update HWID:

    umpire update --from 20150702_rev3 --to 20150702_rev3_newhwid hwid=./hwid.gz

There are also resources:
 - `hwid`: HWID bundle (could be gzipped).
 - `firmware`: The chromeos-firmware script (could be gzipped).
 - `toolkit`: The toolkit file (install_factory_toolkit.run).

Restarting Umpire
-----------------
The docker containers were configured to auto-restart if your machine was
rebooted unexpectedly. If you want to fully restart umpire, try
`setup/cros_docker.sh umpire stop`, `setup/cros_docker.sh umpire run`.

Changing Umpire configuration
-----------------------------
To configure additional services, enter docker and execute `umpire edit` to get
additional commands.

A sample config looks like:

    port: 8080
    rulesets:
    - bundle_id: empty
      note: n/a
      active: true
    services:
      http: {}
      shop_floor: {}
      rsync: {}
    bundles:
    - id: empty
      note: n/a
      payloads: payload.99914b932bd37a50b983c5e7c90ae93b.json

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
   accessible outside Docker. Find them in `/cros_docker/umpire/$BOARD/log`.

   For example, nginx logs are in:

       cd /cros_docker/umpire/$BOARD/log
       less httpd_access.log
       less httpd_error.log

2. Umpire itself. Logs are handled by docker.

       docker logs umpire_$BOARD
