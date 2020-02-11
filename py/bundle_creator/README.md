# Easy Bundle Creation

[TOC]

## Introduction

Easy Bundle Creation is a backend service that accepts RPC calls, creates the
factory bundles and supports downloading the created bundles.

## File location

### ChromeOS repository

* `$(factory-repo)/py/bundle_creator` contains the main codebase.
* `$(factory-repo)/deploy/bundle_creator.sh` is the helper script to
  deploy the project.
* `$(factory-private-repo)/config/bundle_creator` contains all the
  confidential configurations.

## Build & Deploy

To deploy the app engine, run:

```
(factory-repo)$ ./deploy/bundle_creator.sh deploy-appengine ${deployment_type}
(factory-repo)$ ./deploy/bundle_creator.sh deploy-appengine-legancy ${deployment_type}
```

To deploy the compute engine, run:

```
(factory-repo)$ ./deploy/bundle_creator.sh build-docker ${deployment_type}
(factory-repo)$ ./deploy/bundle_creator.sh deploy-docker ${deployment_type}
(factory-repo)$ ./deploy/bundle_creator.sh create-vm ${deployment_type}
```
