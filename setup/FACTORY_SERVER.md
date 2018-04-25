# Chrome OS Factory Server

This document explains what is the Chrome OS Factory Server, how to install
and how to use it.

[TOC]

## Introduction

The Chrome OS Factory Server is a collection of software components running on a
server deployed in factory manufacturing line, as the single portal for DUTs
(device under test) for accessing shop floor backends, storing logs, syncing
system time, and many other "server" related services.

Currently the server is a [Docker](https://www.docker.com/) image containing
following components:

- [Dome](../py/dome/README.md), the web based front end for accessing server.
- [Umpire](../py/umpire/README.md), provides imaging and partial updates to
    software, and also controls other services.
- [Overlord](../go/src/overlord/README.md), a remote monitoring service.
- [Instalog](../py/instalog), a robust logging pipeline.
- [DKPS](../py/dkps), a service for managing keys for provisioning.

And usually you will only need to access the server via browser using
http://localhost:8000 (default port for Dome), which can configure all other
components.

## Prerequisite

### Hardware

The factory server can run on any machines that can run
[Docker](http://docker.io), but we'd recommend a dedicated host with large
storage.

#### Minimal requirements

- CPU: x86-64 CPU
- Memory: Just enough to run host OS, Docker, nginx + django; for example 2G.
- Storage: Enough space for logs and resources in bundles; for example 256G.

#### Recommendation for premium projects

This is the recommendation for building high-end products like Pixelbook.

- Memory: 16G
- Storage: 4T
- CPU: Intel Core i7 or Xeon E5 series or an faster x86-64 CPU

### Software

[Docker](http://docker.io) currently supports Windows, Linux and MacOS, but the
recommended setup is an x86-64 machine running Linux Server, which has best
performance for production servers.

The deployment script `cros_docker.sh` currently supports Linux and MacOS so you
can use both systems for development or experiments. It is possible to run
Factory Server on Windows, but you have to deploy manually and that is not
officially supported.

#### Linux Server

1. Current recommendation is to use [Ubuntu Linux 16.04.1 server](
   http://releases.ubuntu.com/16.04/ubuntu-16.04.1-server-amd64.iso) (xenial).

2. During installation, please specify the system to be formatted by GPT instead
   of MBR to gain maximum disk space.

3.  Docker saves everything in `/var/lib` and the Chrome OS Factory Server saves
    its own data in `/cros_docker` so you should make sure the partition is
    large enough for these two folders. A simple solution is to not creating
    any additional partitions (only have `/` and `/boot`).

#### Mac OSX

1. If you run factory sever on Mac OSX, the shared folder is in
   `${HOME}/cros_docker` instead of `/cros_docker`, for example
   `/Users/admin/cros_docker`.

#### Docker

1. If your server is running recommended Ubuntu, simply run following commands
   to install Docker:

       sudo apt-get update && sudo apt-get install docker.io

   Otherwise, read [Docker docs](https://docs.docker.com/engine/installation/)
   to find the right instruction for your server.

2. Type `docker version` and make sure your Docker server is ready, and the
   version is newer than `1.10.3`

## Installation

### Get deployment script

The deployment of all Chrome OS Factory Server components are managed by a
[`cros_docker.sh`](./cros_docker.sh) script.  To obtain that, you have three
choices - just choose one of them:

1. Download latest version from web. Make sure you have `curl` and `base64`
   then type following commands:

       curl -L http://goo.gl/gKCyo1 | base64 --decode >cros_docker.sh
       sh ./cros_docker.sh update  # Self-test and change file permission.

2. Or, check out from factory software repository:

       git clone https://chromium.googlesource.com/chromiumos/platform/factory
       cd factory/setup

   Now you have `./cros_docker.sh`.

3. Or, (only for Chrome OS partners) download the prepared factory bundle from
    [CPFE](https://www.google.com/chromeos/partner/fe/#home), extract, then
    find the script in `setup` folder.

### Download and install factory server

1. Run following command to download the Docker image on a machine which
   has access to internet:

       ./cros_docker.sh pull

2. If your target server machine does not have public network, copy
    `cros_docker.sh` and files listed on the screen to the target computer.
3. On the target server machine, run following command to load Docker images:

       ./cros_docker.sh install

4. Run following command to start the front end [Dome](../py/dome/README.md).

       ./cros_docker.sh run

### Update deployment script and server images

The version of server image is tracked inside deployment script
`cros_docker.sh`. To update deployment script and server images to latest
version, do:

     ./cros_docker.sh update

Then repeat the steps in previous section to update Docker images.

*** note
Note: Umpire instances already created won't be updated automatically.
To update, go to Dome console and enter created projects, click the "DISABLE"
action button then "ENABLE" again using same port, then click the "CREATE A NEW
UMPIRE INSTANCE" button.
***
