ChromeOS Probe Info Service
===========================

[TOC]

## Overview

This project is still under active development.

Probe Info Service is an AppEngine service that manages component probe
statements.  The service leverages data from AVL system to generate the
corresponding probe statements for the [probe tool](http://go/cros-probe)
automatically.  It also brings-up self-service mechanism to verify the
data, and provides rich exception handling process to handle corner cases.

## Folder Structure

* `$(factory-repo)/py/probe_info_service` contains the main code base.
* `$(factory-repo)/deploy/probe_info_service.sh` is the helper script to
  deploy or test the project.
* `$(factory-private-repo)/config/probe_info_service` contains all the
  confidential configurations.

## Deployment

To deploy the service to staging environment, run

```
(factory-repo)$ ./deploy/probe_info_service.sh deploy staging
```

## Testing

### Unittest

Unittests modules are named with suffix `_unittest.py`.  Because the working
environment of Probe Info Service is quite different than the factory framework
on DUT, `make -C $(factory-repo) test` ignores all unittest modules related
to Probe Info Service.  Instead, developers should trigger the tests by
the helper script as follow:

```shell
(factory-repo)$ ./deploy/probe_info_service.sh unittest
```

Or run the specific unittest(s) and dump the log by the following command:

```shell
(factory-repo)$ ./deploy/probe_info_service.sh unittest --dump_logs \
    [<absolute_unittest_module_names>...]
```

### Manual Test

Following command starts the service on `localhost:8080`:

```shell
(factory-repo)$ ./deploy/probe_info_service.sh run
```

To invoke a ProtoRPC method call, one can send the request by `curl` commandline
tool.  For example, following shell commands invoke
`ProbeInfoService.GetProbeSchema`.

```shell
(factory-repo)$ PKG_NAME="cros.factory.probe_info_service.app_engine.stubby_pb2"
(factory-repo)$ BASE_URL="http://localhost:8080/_ah/stubby"
(factory-repo)$ PROTOC_ARGS="-I py/probe_info_service/app_engine stubby.proto"
(factory-repo)$ \
  echo -ne '' \
  | protoc $PROTOC_ARGS --encode="${PKG_NAME}.GetProbeSchemaRequest" <<__EOF__ \
  | curl --data-binary @- "${BASE_URL}/ProbeInfoService.GetProbeSchema" \
  | protoc $PROTOC_ARGS --decode="${PKG_NAME}.GetProbeSchemaResponse"
```

## Development Tip

### Enable the IntelliSense

Some of the messages are defined in `.proto` protobuf file, which makes
the IntelliSense feature of those classes in Python failed by default.
However, developers can still bring the features up by re-using the
deployment flow, in which the `.proto` files are transformed into `.py` files.

The deployment flow roughly consists of following 3 steps:

1. `make -C $(factory-repo)/py/probe_info_service prepare` generates all
   auto-generated files and put them in
   `$(factory-repo)/build/probe_info_service/gen`.
2. `make -C $(factory-repo)/py/probe_info_service _pack` copies all required
   source files into the correct location in a temporary directory in
   preparation of AppEngine deployment.
3. `gcloud app deploy <tmp_dir>/app.yaml` deploys the sources.

To enable IntelliSense, one can specify
`$(factory-repo)/build/probe_info_service/gen` as a path for python libraries
and manual run `make prepare` once `.proto` files are modified.

## Reference

* API Spec: [http://go/cros-probe-info-service-spec]()
* Design Doc: [http://go/cros-probe-info-service-design]()
