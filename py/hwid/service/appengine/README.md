# HWID Service
This folder contains the mandatory files to deploy HWID Service on AppEngine.
Most of the files are porting from [HWID Server](http://go/g3hwidapi) with
modifications to adapt to factory repository.

## Design
The origin HWID Server [Arch Overview](http://go/hwid-server-arch) and
[Design Doc](http://go/hwid-server).

## Important Files
- `app.yaml`: Config file for deploying service on AppEngine.
- `cron.yaml`: Config file for deploying cronjob on AppEngine.
- `${factory_dir}/deploy/cros_hwid_service.sh`: The main script to deploy and
  test HWID Service. Run `cros_hwid_service.sh` for more usage.
- `appengine_config.py`: The very first loading file on AppEngine.
- `app.py`: The API entry point. It defines the API handlers.
- `hwid_api.py`: The HWID API function implementation.

## Run and Deploy

### Environments
There are three environments to deploy to:
1. prod
   - GCP project name: chromeos-hwid
   - AppEngine APP ID: s~chromeos-hwid
   - AppEngine URL: https://chromeos-hwid.appspot.com
   - AppEngine Management Page:
     https://appengine.google.com/?&app_id=s~chromeos-hwid
   - Cloud Storage Bucket:
     https://console.developers.google.com/storage/chromeoshwid/
   - Borgcron Job Sigma: http://sigma/jobs/chromeoshwid
   - Endpoint URL: https://chromeos-hwid.appspot.com/api/chromeoshwid/v1/
2. staging
   - GCP project name: chromeos-hwid-staging
   - AppEngine APP ID: s~chromeos-hwid-staging
   - AppEngine URL: https://chromeos-hwid-staging.appspot.com/
   - AppEngine Management Page:
     https://appengine.google.com/?app_id=s~chromeos-hwid-staging
   - Cloud Storage Bucket:
     https://console.developers.google.com/storage/chromeoshwid-staging/
   - Borgcron Job Sigma: N/A (Job only exists for prod).
   - Endpoint URL:
     https://chromeos-hwid-staging.appspot.com/api/chromeoshwid/v1/
3. local
   - GCP project name: N/A
   - AppEngine APP ID: N/A
   - AppEngine URL: N/A
   - Cloud Storage Bucket:
     https://console.developers.google.com/storage/chromeoshwid-dev/
     (Note: Just the server is local, the bucket is not)
   - Borgcron Job Sigma: N/A
   - Endpoint URL: http://localhost:8080/api/chromeoshwid/v1/

### AppEngine Deployment Flow

1. Make sure the contents of three repos is what you want:
  - [chromeos-hwid](http://go/chromeos-hwid-git/)
  - [factory](http://go/factory-git/)
  - [regions](http://go/regions-git/)

  Normally, we would use ToT: Run `repo sync .` in each repo.

2. Make sure endpoint config is up-to-date. If the interface is not changed,
   you can skip this step and the deployment script will find the latest
   version of config.
```bash
# As endpoint interface changes, you may need to generate the json config of
# Open API settings. Note that ${endpoint_service_name} here is the AppEngine
# URL mentioned above without `https://` schema prefix.
cd ${appengine_dir}
PYTHONPATH=../../../../build/hwid/protobuf_out \
  python ../../../../build/hwid/lib/endpoints/endpointscfg.py \
  get_openapi_spec hwid_api.HwidApi --hostname "${endpoint_service_name}"
# You can then deploy the generated config file `chromeoshwidv1openapi.json`.
gcloud endpoints services deploy chromeoshwidv1openapi.json
```

3. Before deploying to `prod`, you have to deploy to `staging`:
```bash
# If you use Google Cloud Platform for the first time, you may have to
# install gcloud sdk (https://cloud.google.com/sdk/install).  gcloud may ask you
# to register or loging your account.  Please enter your google domain acount.
# It may also ask you to register or login a GCP project account, you can
# use 'chromeos-factory'.  The deploy script will choose the right GCP project
# to deploy.
deploy/cros_hwid_service.sh deploy staging
```

4. Make sure all tests are passed:
```bash
# In chroot: unittest
make test
# Out of chroot: integration test and e2e test
# - Integration test creates a docker image, which may take a long time for the
#   first time running this script.
# - e2e test list is placed at http://go/factory-private-git
deploy/cros_hwid_service.sh test
```

5. If all tests are passed, now we can deploy the HWID Service to `prod`:
```bash
deploy/cros_hwid_service.sh deploy prod
```

6. Open the AppEngine management page, and watch the traffics are not blocked.

### Invoking API
Example request for local environment:
```bash
# Before invoking local API, you have to deploy local env
deploy/cros_hwid_service.sh deploy local
# Now you can test HWID Service locally.
curl http://localhost:8080/api/chromeoshwid/v1/boards
curl --data '{ "hwidConfigContents": "\n\nchecksum: test\n\n" }' \
--dump-header - http://localhost:8080/api/chromeoshwid/v1/validateConfig
```

Example request for staging/prod environment, using HWID `CHROMEBOOK B2A-M5N`:
```bash
curl "${ENDPOINT_URL}/bom/CHROMEBOOK%20B2A-M5N?key=${APIKEY}"
```

Where **${APIKEY}** can be created from **AppEngine Management Page** ->
**APIs & Services** -> **Credentials**.


### Test
```bash
cros_sdk make -C ../platform/factory test  # factory unittests
./deploy.sh test  # integration tests and e2e tests
```

### Log
To view the logs, you have to go to **AppEngine Management Page** ->
**Versions** -> **Diagnose** -> **Logs**

## HWID Database Ingestion Pipeline
The ingestion pipeline helps AppEngine get access to the HWID Database on
Gerrit, there are two stages of the pipeline.
1. Borgcron Job Ingestion
   - Uploads HWID Databse from gerrit to BigStore bucket `[bucket]/staging`
     every day. (code: http://go/chromeos-hwid-ingestion)
2. AppEngine Cronjob Ingestion
   - Validates the HWID Databse files in BigStore bucket `[bucket]/staging`. If
     the file is validated, move the file from `[bucket]/staging` to
     `[bucket]/live`.

## Borgcron Job Deployment
The borgcron job is to periodically(every 24h) upload the latest HWID Database
from git(via git/gerrit-on-borg) to the cloud buckets. Since it is a borgcron
job, we don't port this part to the factory repository. To modify the code and
deploy, please refers to http://go/hwid-server-arch -> **Run & deploy** ->
**Deploying the borgcron job**.
