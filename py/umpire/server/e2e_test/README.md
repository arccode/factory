Integration tests for Umpire docker
===================================

This test should be run by `cros_docker.sh umpire test`.

`cros_docker.sh` is in directory `setup/` under root directory of factory
repository (in `../../../../setup` relative to this directory.)

Terminology
-----------
* Host: The machine where source tree is located.
* Test Docker: The docker where main test script `e2e_test.py` is run.
* Umpire Docker: The Umpire docker instance to be tested, created by the main
                 test script.

Directory structure in source tree
----------------------------------
In directory `py/umpire/server/e2e_test`:
* `e2e_test.py`: The main test script.
* `Dockerfile`: Dockerfile to build Test Docker.
* `requirements.txt`: Dependencies of main test script, would be installed in
                      Test Docker.
* `testdata/umpire`: Data that would be mounted on `/var/db/factory/umpire` in
                     Umpire Docker.
* `testdata/cros_docker`: Data that would be mounted on `/mnt` in Umpire Docker.
* `testdata/config`: Testdata used by main test script.

In directory `setup`:
* `cros_docker.sh`: Shell script used to control factory server services, in
                    particular, Umpire.

Test flow
---------
The test flow is as follows when `cros_docker.sh umpire test` is executed.
* Build the factory server docker image. (Same as `cros_docker.sh build`)
* Build Test Docker from `Dockerfile` in this directory, which copies `py/,
  py_pkg/, bin/, setup/cros_docker.sh` into `/usr/local/factory` in Test
  Docker.
* Start a new Test Docker instance, with a temporary folder on Host stored in
  environment variable `TMPDIR`, and mounted on same path inside Test Docker.
* Inside Test Docker, for each set of test, a new Umpire Docker is created on
  setUpClass, and destroyed on tearDownClass.
* Inside Test Docker, when creating a new Umpire Docker, copy
  `testdata/cros_docker` into `${TMPDIR}/cros_docker/`, `testdata/umpire`
  into `${TMPDIR}/cros_docker/umpire/${PROJECT}/`, and set
  `HOST_SHARED_DIR` environment variable to `${TMPDIR}/cros_docker` when
  calling `cros_docker.sh umpire run` inside main test script.
* The docker service **on Host** would then create Umpire Docker, mount
  `${TMPDIR}/cros_docker` to `/mnt` in Umpire Docker,
  `${TMPDIR}/cros_docker/umpire/${PROJECT}` to `/var/db/factory/umpire` in
  Umpire Docker.
* Test is executed by calling other `cros_docker.sh` commands, and interact
  with Umpire Docker.
