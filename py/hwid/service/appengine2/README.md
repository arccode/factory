# HWID Service Proxy on App Engine

This folder contains HWID Service Proxy on App Engine.

## Overview

HWID Service Proxy is a light-weight wrapper that proxy the protorpc requsts
from user to HWID Service.

### HWID Service Call Graph

![HWID Service Call Graph](../images/hwid_service_call_graph.png)

## Deploy to Local Development Server

1. Install App Engine SDK for Python

  ```shell
  sudo apt-get install google-cloud-sdk-app-engine-python
  ```

2. Compose `config.py` in the appengine2 folder, assume local HWID Service is
   listening to http://127.0.0.1:8181/

  ```python
  GKE_HWID_SERVICE_URL='http://127.0.0.1:8181/'
  ```

3. Start the local development server, assigned the listening port for
   HWID Service Proxy.

  ```shell
  dev_appserver.py --port=${port} app.yaml
  ```

Local Development Server Reference [link](https://goo.gl/V258Gb)

## Deploy to App Engine

Use [cros_hwidservice.sh](../../../../deploy/cros_hwidservice.sh) to deploy

  ```shell
  # Available projects are {prod, staging, dev}
  cros_hwidservice.sh -p ${project} appengine deploy
  ```
