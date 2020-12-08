# DRM Keys Provisioning Server (DKPS) User Guide

[TOC]


## Introduction

DKPS (DRM Keys Provisioning Server) provides 3 core functions:
1. allows the `uploader` to upload DRM keys to the server securely,
2. stores the DRM keys securely, and
3. allows the `requester` to request DRM keys from the server securely.
DKPS provides both python RPC call interface or convenient python helper scripts
to achieve the goals.

The `uploder` will typically be an OEM (Original Equipment Manufacturer), and
the `requester` will typically be an ODM (Original Design Manufacturer).


## Prerequisite

You'll need python and GnuPG to run the server.

```sh
sudo apt-get install python python-gnupg gnupg`
```

*** aside
[optional] To make GnuPG key generation faster, you'll need `rng-tools`. This
step optional, but if you don't install `rng-tools`, your system may take a very
long time to initialize the server, because it can not generate random numbers
efficiently.
***

```sh
sudo apt-get install rng-tools
```

Check out DKPS source
[here](https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/py/dkps/).

You'll also need the uploader and requester's GnuPG exported public key files.


## Generating GnuPG Keys for Uploader and Requester

If you already have GnuPG keys for uploader and requester, you can skip this
section.

*** note
Note: for security reason, the uploader should generate the uploader's GnuPG key
themselves, and the requester should generate the requester's GnuPG key
themselves. The uploader should __NOT__ help the requester generating the
requester's GnuPG key, and the requester should __NOT__ help the uploader
generating the uploader's GnuPG key, either. Unless the uploader and the
requester are the same.
***

To generate the uploader's GnuPG key:
```sh
mkdir gnupg  # create a temporary directory
gpg --homedir gnupg --gen-key
# follow the instruction to generate the key
gpg --homedir gnupg --export -a >uploader.pub
gpg --homedir gnupg --export-secret-keys -a >uploader.key
rm -rf gnupg  # remove temporary directory
```
Keep `uploader.key` in a safe place, where only you can access, and send
`uploader.pub` to the person who is going to set up DKPS server.

To generate the requester's GnuPG key, follow the instruction above, change
`uploader` to `requester`.


## DKPS Structure

- `dkps.py` the main DKPS server application.
- `requester_helper.py` helper module for requesting DRM keys from the server.
- `uploader_helper.py` helper module for uploading DRM keys to the server.
- `filters` folder that contains filter modules.
- `parsers` folder that contains parser modules.
- `sql` SQL file for initializing the database.


## Initializing the Server

Run the following command:

```python
python dkps.py init
```

This will create a folder `gnupg`, a file `dkps.db`, and the log file
`dkps.log`.

`gnupg` holds the server's GnuPG key.

`dkps.db` is the database file, so better back it up from time to time.

`dkps.log` is the log file. It will grow. If there is no problem with your
server, you can truncate this file at any time.


## Exporting DKPS Server's GnuPG Public Key

Run the following command:
`gpg --homedir gnupg --export -a >server.pub`

The server's GnuPG public key will be saved in `server.pub`. Send this file to
the uploader and requester, they'll need this file later.


## Writing a Parser Module

A parser module parses the raw DRM key list file into python list of DRM keys
(also called "de-serialization").

For example, if the raw DRM key list file is in JSON format:
```json
[{'key': '123'}, {'key': '456'}]
```

Then the parser module could be:
```python
import json
def Parse(serialized_drm_key_list):
  return json.loads(serialized_drm_key_list)
```
which just parses the JSON string and converts it to a python list.


## Writing a Filter Module

A filter module lets you modify the raw DRM keys before actually saving to the
database.

For example, if you want to add `abc` to every of the DRM keys before saving
into the database:
```python
def Filter(drm_key_list):
  return map(lambda k: 'abc' + k, drm_key_list)
```

If you don't need to modify the DRM keys, you can use `sample_filter.py`. The
filter does nothing but return `drm_key_list` directly.


## Adding a New Project

Now the server has been initialized, time to create a new project:
```sh
python dkps.py add -n ${NAME} \
  -u ${UPLOADER_GPG_KEY_FILE} -r ${REQUESTER_GPG_KEY_FILE} \
  -p ${NAME_OF_THE_PARSER_MODULE} -f ${NAME_OF_THE_FILTER_MODULE}
```

For example, if your project's name is `superman`, and have the uploader's GnuPG
public key as `uploader.pub`, requester's GnuPG public key as `requester.pub`,
and will use `parsers/widevine_parser.py` as the parser,
`filters/sample_filter.py` as the filter, then:
```sh
python dkps.py add -n superman \
  -u uploader.pub -r requester.pub \
  -p widevine_parser.py -f sample_filter.py
```

Your project has been set up! You can type:
```sh
python dkps.py list
```
to see if the project has been added correctly.


## Starting to Serve DRM Keys

```sh
python dkps.py listen
```
and leave it there.

The default port is 5438, you can change this using the `--port` argument. For
example, to change the listen port to 1234:
```sh
python dkps.py listen --port 1234
```


## Uploading DRM Keys

```sh
python uploader_helper.py \
  --server_ip ${DKPS_SERVER_IP} \
  --server_port ${DKPS_SERVER_PORT} \
  --server_key_file_path ${DKPS_SERVER_PUBLIC_GPG_KEY_FILE} \
  --uploader_key_file_path ${UPLOADER_GPG_PRIVATE_KEY_FILE} \
  --passphrase_file_path ${PASSPHRASE_FILE_PATH} \
  upload ${DRM_KEYS_FILE_PATH}
```

By default `${DKPS_SERVER_PORT}` is 5438 (if you didn't change the port in the
[Starting to Serve DRM Keys](#starting-to-serve-drm-keys) section.)

`${DKPS_SERVER_PUBLIC_GPG_KEY_FILE}` is the server's GnuPG public key exported
in the [Exporting DKPS Server's GnuPG Public
Key](#exporting-dkps-server's-gnupg-public-key) section.

`${UPLOADER_GPG_PRIVATE_KEY_FILE}` is the key file (the private one, i.e.
`uploader.key`, not `uploader.pub`) generated in [Generating GnuPG Keys for
Uploader and Requester](#generating-gnupg-keys-for-uploader-and-requester)
section.

If you have set up a passphrase when generating the uploader's GnuPG key, you
need to save the passphrase into a file and give the file path to
`${PASSPHRASE_FILE_PATH}`.

`${DRM_KEYS_FILE_PATH}` is the path to raw DRM keys file.


## Requesting DRM Keys

```sh
python requester_helper.py \
  --server_ip ${DKPS_SERVER_IP} \
  --server_port ${DKPS_SERVER_PORT} \
  --server_key_file_path ${DKPS_SERVER_PUBLIC_GPG_KEY_FILE} \
  --requester_key_file_path ${REQUESTER_GPG_PRIVATE_KEY_FILE} \
  --passphrase_file_path ${PASSPHRASE_FILE_PATH} \
  request ${DUT_SERIAL_NUMBER}
```

By default `${DKPS_SERVER_PORT}` is 5438 (if you didn't change the port in the
[Starting to Serve DRM Keys](#starting-to-serve-drm-keys) section.)

`${DKPS_SERVER_PUBLIC_GPG_KEY_FILE}` is the server's GnuPG public key exported
in the [Exporting DKPS Server's GnuPG Public
Key](#exporting-dkps-server's-gnupg-public-key) section.

`${REQUESTER_GPG_PRIVATE_KEY_FILE}` is the key file (the private one, i.e.
`requester.key`, not `requester.pub`) generated in [Generating GnuPG Keys for
Uploader and Requester](#generating-gnupg-keys-for-uploader-and-requester)
section.

If you have set up a passphrase when generating the requester's GnuPG key, you
need to save the passphrase into a file and give the file path to
`${PASSPHRASE_FILE_PATH}`.

`${DUT_SERIAL_NUMBER}` is a string (DUT's serial number). If you give the same
serial number, the DKPS server will always return the same DRM key. So it's fine
to ask multiple times.
