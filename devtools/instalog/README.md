# Instalog Scripts

Scripts in this directory helps you find data from Google Cloud easily.

## `devtools/instalog/get_attachments.py`

### Guide for Linux OS

#### Installing the Google Cloud SDK

*   https://goto.google.com/cloudsdk (for Googlers)
*   https://cloud.google.com/sdk/downloads (for Others)

#### Setting Up the Google Cloud SDK

*   Run `gcloud init` and choose the project: `chromeos-factory`.

#### Downloading `devtools/instalog/get_attachments.py`

*   Run the following command
```
    curl --location --fail "https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/devtools/instalog/get_attachments.py?format=TEXT" |
    base64 --decode > get_attachments.py &&
    chmod +x get_attachments.py
```
*   Or copy the script from [here](get_attachments.py?format=TEXT), and save as
    `get_attachments.py`.

#### Testing

*   Run `./get_attachments.py 'a01' 'TESTID'`.
*   Check if there has a file in the directory `factory_attachments`.
*   Check the content in the file is
```
Hello World!
Hello ChromeOS Factory!
```
*   If it is, congratulation; otherwise, check the logs when running the
    script.

### Guide for Windows OS

#### Installing the Google Cloud SDK

1.  https://cloud.google.com/sdk/downloads
2.  Download Windows with Python bundled, if you don't have Python2.7.
3.  Extract the contents of the file to any location on your file system.
4.  Run `google-cloud-sdk\install.bat`

#### Setting Up the Google Cloud SDK

*   Run `google-cloud-sdk\bin\gcloud init` and choose the project:
    `chromeos-factory`.

#### Downloading `devtools/instalog/get_attachments.py`

*   Copy the script from [here](get_attachments.py?format=TEXT), and save as
    `get_attachments.py`.

#### Testing

*   Run `google-cloud-sdk\platform\bundledpython\python.exe get_attachments.py
    --bq_path google-cloud-sdk\bin\bq.cmd
    --gsutil_path google-cloud-sdk\bin\gsutil.cmd
    a01 TESTID`

### Usage

*   Please run `./get_attachments.py --help` for the details.

### Name Format

*   All attachments are named by
    `ServerReceiveTime_AttachmentKey_SerialNumber_MD5Sum`
