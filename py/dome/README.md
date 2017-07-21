# Dome User Guide

Dome: The Factory Server Management Console

## Introduction to Dome

Dome is our new factory management console. On the factory server side, we have
different projects responsible for different parts before: Shopfloor, Umpire,
DKPS, Instalog, etc. They all have their own ways to manage, and require
knowledge of the command line interface. Therefore, Dome was born: management
console for all things in just one place, and best of all, it's GUI. In the
future, you no longer need to set up Shopfloor, Umpire, or Instalog
independently. You set up Dome, and let Dome help you finish all the tasks for
you.

## Prerequisite

You need docker installed on the target computer (which requires internet
access for a while).

1. Recommend to use [Ubuntu 16.04.1 server](
   http://releases.ubuntu.com/16.04/ubuntu-16.04.1-server-amd64.iso) (xenial).

2. Install Docker:

   ```shell
   sudo apt-get update && sudo apt-get install docker.io
   ```

3. Type `docker version` and make sure your server version is newer than `1.9.1`

4. Dome is a web-based program, if you want to use it on the same machine,
   you’ll need the desktop environment. Run

   ```shell
   sudo apt-get install ubuntu-desktop chromium-browser
   ```

   to install the desktop environment and Chromium browser.

*Note: the default Docker version shipped with Ubuntu 14.04 is too old. If you
really have to use Ubuntu 14.04, you'll have to install newer Docker on it
yourself. See https://docs.docker.com/engine/installation/linux/ubuntulinux/*

## Deploying Dome

### Get setup script

The deployment of all factory server components are managed by a
`cros_docker.sh` script. To obtain that, you have three choices; just choose one
of them:

1. Download latest version from web. Make sure you have `curl` and `base64`
   then:
```sh
url=https://chromium.googlesource.com/chromiumos/platform/factory/+/master/setup/cros_docker.sh
curl "${url}?format=TEXT" | base64 -d >cros_docker.sh
sh ./cros_docker.sh update
```

2. Check out from factory repository:
```sh
git clone https://chromium.googlesource.com/chromiumos/platform/factory
cd factory/setup
```
   Now you have `./cros_docker.sh`.

3. Download the prepared factory bundle from
    [CPFE](https://www.google.com/chromeos/partner/fe/#home), extract, then
    `cd` to `setup` folder to find the script.

### Download and install factory server images
1.  Run `./cros_docker.sh pull` to download the docker images.
2.  If your target server machine does not have public network, copy
    `cros_docker.sh` and files listed on the screen to the target computer.
3.  On the target server machine, run `./cros_docker.sh install` to load docker
    images.
4.  Run `./cros_docker.sh run` to start Dome containers.

### Access Dome Web User Interface
Open your browser to port 8000 of the Dome server, and you should see the
welcome page. For example, if you're using the same machine and had the desktop
environment set up, open the browser to `http://localhost:8000`.

*** note
**Note**: using Chrome/Chromium is highly recommended. If you want to use other
browsers such as Firefox, you'll have to make sure the timeout setting is long
enough or you're likely to get an timeout error when uploading bundle files
since they're normally very large.
***

### Update setup script and server images
The version of server image is tracked inside setup script. To update setup
script and server images to latest version, do:
```sh
./cros_docker.sh update
```
Then repeat the steps in "Download and install factory server images" to update
Dome.

*** note
One thing to note is that already created Umpire instances won't be updated
automatically. To update, go to Dome and select project, click the "DISABLE"
action button then "ENABLE" again using same port, then click the "CREATE A NEW
UMPIRE INSTANCE" button.
***
