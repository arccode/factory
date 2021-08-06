# Overlord Deployment Guide

# Objective

The goal of this document is to provide deployment guidance to the
[Overlord][Overlord Design Doc] factory monitor system.

# Deployment

### Prerequisites

You need a computer that can run docker and python3.6+. We recommend using
Ubuntu 18.04+.

Add current user to the "docker" group, then you can run docker command without
sudo.
```bash
sudo usermod -aG docker ${USER}
```

Intstall the following packages:
```bash
pip3 install jsonrpclib-pelix ws4py
```

### Get the deployment script

The Overlord source code resides in the chromiumos factory repository. You can
clone the factory git repo without the entire chromiumos source tree:

```bash
$ git clone https://chromium.googlesource.com/chromiumos/platform/factory
```

Then you can find the deployment script `setup/cros_docker.sh`.

### Set up Overlord

```bash
$ cd factory/setup
$ ./cros_docker.sh overlord setup
```
You need to provide the following info at this step:
1. Account / password
    - This is Overlord's user account.
2. IP
    - Overlord's IP

After the setup, the setup script will print some instructions for you to set up
the browser certificate. But this step is optional.

### Run Overlord

```bash
$ ./cros_docker.sh overlord run
```

You can access the Overlord server at `https://${IP}:9000`.

# Dashboard feature

This feature integrates the DUT's testing framework into Overlord server. Long
story short:
1. DUT can connect to Overlord and report their test status.
2. Users can view the test status in Overlord dashboard UI.

Please refer to the [user manual guide][Dashboard User Manual] for more details.

-----
# Others

### Ghost Clients

The clients are called `ghost` in the Overlord framework. There are currently
two implementations, one implemented in python and the other implemented in go.
The python version can be found under the factory source repository:
`py/tools/ghost.py`; while the go version is under `go/src/overlord/ghost.go`
which is built along side with the `overlordd` binary under `go/bin`.

#### How to upgrade ghost client

The recommended way is to upgrade the toolkit with upgraded ghost client through
shopfloor. This prevents most of the compatibility issues.

### Internal Docs

1. [Overlord Design Doc][Overlord Design Doc]
2. [Dashboard Design Doc](http://go/overlord-dashboard)

[Overlord Design Doc]: http://go/overlord-doc
[Dashboard User Manual]:
https://docs.google.com/document/d/1X_ELnv4OFuSY7xAeVn5m_2Eo6sMj0dMgfWzY97xHH40/edit?resourcekey=0-S2X0Gp4ehe_m9i_INZqZLA#heading=h.55w5uj6ylsnt
