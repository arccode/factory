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

To deploy Dome:

1.  Download the factory bundle from
    [CPFE](https://www.google.com/chromeos/partner/fe/#home), extract it.
2.  Find the Dome setup script (`dome.sh`) in the `setup` folder.
3.  Run `./dome.sh pull` to download the docker images.
4.  Copy `dome.sh` and files listed on the screen to the target computer.
5.  Run `./dome.sh install` to load docker images.
6.  Run `./dome.sh run` to start Dome containers.

Open your browser to port 8000 of the Dome server, and you should see the
welcome page. For example, if you're using the same machine and had the desktop
environment set up, open the browser to `http://localhost:8000`.

*Note: using Chrome/Chromium is highly recommended. If you want to use other
browsers such as Firefox, you'll have to make sure the timeout setting is long
enough or you're likely to get an timeout error when uploading bundle files
since they're normally very large.*
