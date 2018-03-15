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
- `deploy.sh`: The main script to deploy and test HWID Service. Run `deploy.sh`
  for more usage.
- `appengine_config.py`: The very first loading file on AppEngine.
- `app.py`: The API entry point. It defines the API handlers.
- `hwid_api.py`: The HWID API function implementation.

## Run and Deploy

### Environments
There are three environments to deploy to:
1. prod
   - AppEngine APP ID: s~google.com:chromeoshwid
   - AppEngine URL: https://chromeoshwid.googleplex.com
   - AppEngine Management Page:
     https://appengine.google.com/?&app_id=s~google.com:chromeoshwid
   - Cloud Storage Bucket:
     https://console.developers.google.com/storage/chromeoshwid/
   - Borgcron Job Sigma: http://sigma/jobs/chromeoshwid
   - APIary Endpoint URL: https://www.googleapis.com/chromeoshwid/v1/
2. staging
   - AppEngine APP ID: s~google.com:chromeoshwid-staging
   - AppEngine URL: https://chromeoshwid-staging.googleplex.com/
   - AppEngine Management Page:
     https://appengine.google.com/?app_id=s~google.com:chromeoshwid-staging
   - Cloud Storage Bucket:
     https://console.developers.google.com/storage/chromeoshwid-staging/
   - Borgcron Job Sigma: N/A (Job only exists for prod).
   - APIary Endpoint URL:
     https://www-googleapis-staging.sandbox.google.com/chromeoshwid/v1/
3. local
   - AppEngine APP ID: N/A
   - AppEngine URL: N/A
   - Cloud Storage Bucket:
     https://console.developers.google.com/storage/chromeoshwid-dev/
     (Note: Just the server is local, the bucket is not)
   - Borgcron Job Sigma: N/A
   - APIary Endpoint URL: N/A

### AppEngine Deployment
Use `deploy.sh` script:
```bash
./deploy.sh deploy [prod|staging|local]
```

### Invoking API
Example request for local environment:
```bash
curl http://localhost:8080/_ah/api/chromeoshwid/v1/boards
curl --data '{ "hwidConfigContents": "\n\nchecksum: test\n\n" }' \
--dump-header - http://localhost:8080/_ah/api/chromeoshwid/v1/validateConfig
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
     every day. (code: https://go/chromeos-hwid-ingestion)
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

## Changing the APIary Endpoint Configuration
APIary publishes chromeoshwid API from AppEngine to google domain.
The APIary configuration file is stored in the google3. To change the config,
please refers to https://go/hwid-server-arch -> **Run & deploy** ->
**Changing the Apiary Configuration**.

