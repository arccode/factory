# Umpire

Umpire, standing for *Unified MES Proxy, Imaging, and Reimaging Engine*, is an
unified service management framework to serve Chrome devices' manufacturing
process, including image downloading, factory testing, finalization, and
uploading of events and reports.

Umpire is created as a daemon with command-line tool. A web-based management
console (with better deployment process) is created as standalone project
[Dome](../dome/README.md).

Umpire controls what it serves by JSON configuration file. To make changes, you
can do `umpire edit`. After editing, it automatically runs command
`umpire deploy` so the new configuration is activated.

Data generated (or the resources to be delivered) are stored in
`/var/db/factory/umpire/.....` inside Docker, and
`/cros_docker/umpire/$PROJECT/.....` outside Docker.

## Prerequisite

1. You need [Docker](http://docker.io) installed on the target computer. Read
   [Factory Server](../../setup/FACTORY_SERVER.md#Prerequisite) for more
   details.

## Installation

Umpire is one of the component bundled in Chrome OS Factory Server package, so
please follow the steps in
[Factory Server](../../setup/FACTORY_SERVER.md#Installation).

## Using Umpire

Umpire can be configured using [Dome](../dome/README.md) which provides a web
interface. Please follow Dome user guides to access Umpire.

# Trouble shooting

This section is for advanced developers, to access Umpire directly without using
Dome.

## Check if Umpire is running properly

Enter Docker instance shell and do `umpire status`.

    setup/cros_docker.sh umpire shell
     umpire status

A typical output:

    Active config:
    {
      ...
    }

## Deploy a factory bundle

Umpire by default comes with empty bundle. To feed the images (with test image,
release image, toolkit, firmware, hwid, ... etc) you have to first prepare it
with the [`finalize_bundle`](../../setup/BUNDLE.md) command. When a bundle file
is available, do:

    sudo cp factory_bundle.zip /cros_docker
    setup/cros_docker.sh umpire shell
     umpire import-bundle /mnt/factory_bundle.zip
     umpire edit  # and mark the bundle in rulesets as active.

## Update resources

You have to first copy the new file into `/cros_docker` (which can be found as
`/mnt` inside Docker) then notify Umpire to use them using `umpire update`
command. Example:

    setup/cros_docker.sh umpire shell
     umpire update --from 20150702_rev3 --to 20150702_rev3_newtoolkit \
       toolkit=/mnt/install_factory_toolkit.run
     umpire edit

You should see a new bundle name `20150702_rev3_newtoolkit`. Put it in
`ruleset` section and active it.

To update HWID:

    umpire update --from 20150702_rev3 --to 20150702_rev3_newhwid hwid=./hwid.gz

There are also resources:
 - `hwid`: HWID bundle (could be gzipped).
 - `firmware`: The `chromeos-firmware` script (could be gzipped).
 - `toolkit`: The toolkit file (`install_factory_toolkit.run`).

## Restart

The Docker containers were configured to auto-restart if your machine was
rebooted unexpectedly. If you want to fully restart Umpire, try
`setup/cros_docker.sh umpire stop`, `setup/cros_docker.sh umpire run`.

## Change configuration

To configure additional services, enter Docker and execute `umpire edit` to get
additional commands.

A sample configuration (in JSON) looks like:

    {
      "bundles": [
        {
          "id": "empty",
          "note": "n/a",
          "payloads": "payload.99914b932bd37a50b983c5e7c90ae93b.json"
        }
      ],
      "rulesets": [
        {
          "active": true,
          "bundle_id": "empty",
          "note": "n/a"
        }
      ],
      "services": {
        "shop_floor": {
          "service_url": "http://localhost:8090"
        }
      }
    }

## Rule-based Update

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

## Get logs
There are two places for logs of Umpire.

1. Services hosted by Umpire, especially shop floor proxy. The logs are
   accessible outside Docker. Find them in `/cros_docker/umpire/$PROJECT/log`.

   For example, nginx logs are in:

       cd /cros_docker/umpire/$PROJECT/log
       less httpd_access.log
       less httpd_error.log

2. Umpire itself. Logs are handled by Docker.

       docker logs umpire_$PROJECT
