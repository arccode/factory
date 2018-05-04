# HWID Service Tests
This folder contains the mandatory tests for deploying HWID Service.


## AppEngine Integration Test
Creates an docker image which has AppEngine-like environments, and processes
tests over it. The image contains several python packges, including:
  - google-gcloud-sdk
  - GoogleAppEngineCloudStorageClient
  - webapp2
  - webtest

### Test Procedure
1. Integration test driver `integration_test.py` builds an AppEngine integrated
   docker image by calling `deploy/cros_hwid_service.sh build`.
2. Runs the docker image.
3. After the docker image starts up, it then runs all tests
  `py/hwid/service/appengine/*_test.py`.

### Adds Test
Place your test in the `py/hwid/service/appengine/` and suffixed with `_test.py`

### Runs Test
To run the test, you can type:
```
  ./integration_test.py
```


### Operates in the Test Environemnt
You can also enter the environment to do some test.
```
  deploy/cros_hwid_service.sh build
  docker run -it $(docker ps -lq) /bin/bash
```
The factory root is at `/usr/src/cros/factory`


## AppEngine End-To-End Test
Running end-to-end tests.

### Test Procedure
Before running the e2e_test, you have to deploy HWID Service staging by
`cros_hwid_service.sh deploy staging`.
1. Loads the test config in [factory-private][1] repository.
2. Runs the tests described in the config.

### Adds Test
To add tests, you have to modify config file
`factory-private/config/hwid/service/appengine/test/e2e_test.json`.

[1]: https://chrome-internal.googlesource.com/chromeos/platform/factory-private
