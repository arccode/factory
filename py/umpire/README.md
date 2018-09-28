# Umpire

Umpire, standing for *Unified MES Proxy, Imaging, and Reimaging Engine*, is an
unified service management framework to serve Chrome devices' manufacturing
process, including image downloading, factory testing, finalization, and
uploading of events and reports.

Umpire is created as a daemon. A web-based management console (with better
deployment process) is created as standalone project [Dome](../dome/README.md).

Umpire controls what it serves by JSON configuration file.

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

## Enter Docker instance shell

    setup/cros_docker.sh umpire shell

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
