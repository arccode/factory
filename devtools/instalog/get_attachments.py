#!/usr/bin/env python3
#
# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""
'get_attachments' is a tool to find Testlog attachment files from
BigQuery / GCS across a given date range, and to save them to disk.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys


DATE_FORMAT = '%Y%m%d%H%M%S'
HASH_FILE_READ_BLOCK_SIZE = 1024 * 64  # 64kb
GSUTIL_TEST_PERMISSION_PATH = 'gs://chromeos-localmirror-private/testing/'
PROJECT_ID = 'chromeos-factory'
DEFAULT_START_TIME = '1970-01-01'
DEFAULT_END_TIME = '2100-12-31'
DEFAULT_TARGET_DIR = 'factory_attachments'
DEFAULT_BQ_PATH = 'bq'
DEFAULT_GSUTIL_PATH = 'gsutil'
DEFAULT_SERIAL_NUMBER_KEY = 'serial_number'


def CheckVersion(args):
  print('Checking your gsutil version...')
  subprocess.check_call([args.gsutil_path, '--version'])
  print('Checking your Storage permission...')
  subprocess.check_call([args.gsutil_path, 'ls',
                         'gs://%s/%s' % (PROJECT_ID, args.dataset_id)])

  print('Checking your bq version...')
  subprocess.check_call([args.bq_path, 'version'])
  print('Checking your BigQuery permission and BigQuery dataset ID...')
  subprocess.check_call([args.bq_path, 'show',
                         '--project_id', PROJECT_ID,
                         '--dataset_id', args.dataset_id])
  print()


def RunQuery(args):
  # We don't use parameterized query because the web UI doesn't support it.
  query_statement_words = [
      'SELECT',
      '    attachment.path AS remote,',
      '    FORMAT_TIMESTAMP("%s", time) AS server_time,',
      '    attachment.key AS attachment_key,',
      '    (',
      '        SELECT serialNumber.value',
      '        FROM UNNEST(data.serialNumbers) AS serialNumber',
      '        WHERE serialNumber.key="%s"',
      '    ) AS serial_number',
      'FROM',
      '    `%s.%s.testlog_events` AS data,',
      '    UNNEST(data.attachments) AS attachment',
      'WHERE',
      '    attachment.key LIKE "%%%s%%" AND',
      '    time >= TIMESTAMP("%s") AND',
      '    time < TIMESTAMP("%s")']
  query_statement = '\n'.join(query_statement_words)
  query = query_statement % (
      DATE_FORMAT, args.serial_number_key, PROJECT_ID, args.dataset_id,
      args.attachment_key, args.start_date, args.end_date)

  print('Execute the query, you can also copy-paste the following query to\n'
        'https://bigquery.cloud.google.com')
  print('-' * 37 + 'QUERY' + '-' * 38 + '\n' + query + '\n' + '-' * 80 + '\n')

  p = subprocess.Popen(
      [args.bq_path, 'query', '--max_rows', '1000000', '--nouse_legacy_sql',
       '--format', 'json'],
      stdin=subprocess.PIPE,
      stdout=subprocess.PIPE,
      encoding='utf-8')
  result_json, stderrdata = p.communicate(query)
  if p.returncode:
    print('Query Failed!')
    print(stderrdata)
    sys.exit(1)
  print()

  return result_json


def Filter(args, results):
  return [row
          for row in results
          if row['serial_number'] in args.serial_number]


def Download(args, results):
  tmp_dir = os.path.join(args.target_dir, 'tmp')
  remote_list = []
  for row in results:
    row['tmp'] = os.path.join(tmp_dir, row['remote'].split('/')[-1])
    remote_list.append(row['remote'])

  # Remove duplicates in the remote_list.
  remote_list = list(set(remote_list))

  for i in range(0, len(remote_list), 100):
    print('Downloading the %d-%d of %s attachments...' %
          (i, min(i + 100, len(remote_list)) - 1, len(remote_list)))
    commands = [args.gsutil_path, '-m', 'cp', '-n']
    commands.extend(remote_list[i:i+100])
    commands.append(tmp_dir)
    subprocess.check_call(commands)


def FileHash(path):
  file_hash = hashlib.md5()
  with open(path, 'rb') as f:
    for chunk in iter(lambda: f.read(HASH_FILE_READ_BLOCK_SIZE), b''):
      file_hash.update(chunk)
  return file_hash.hexdigest()


def CopyAndDelete(args, results):
  tmp_dir = os.path.join(args.target_dir, 'tmp')
  for row in results:
    file_name = '%s_%s_%s_%s' % (row['server_time'], row['attachment_key'],
                                 row['serial_number'] or 'NoSerialNumber',
                                 FileHash(row['tmp']))
    local = os.path.join(args.target_dir, file_name)
    print(row['remote'] + ' --> ' + local)
    shutil.copyfile(row['tmp'], local)
  shutil.rmtree(tmp_dir)


def main():
  parser = argparse.ArgumentParser(
      formatter_class=argparse.RawDescriptionHelpFormatter,
      description='Attachment downloader script',
      epilog='Common errors are permission and installation.\n'
             'Please check https://cloud.google.com/sdk/docs/ to\n'
             '  (1) update your gsutil to 4.26 and BigQuery CLI to 2.0.24\n'
             '  (2) authorize gcloud by "gcloud init" or "gcloud auth login"')
  parser.add_argument(
      'dataset_id',
      help='The BigQuery dataset ID.  Example: a01')
  parser.add_argument(
      'attachment_key',
      help='The attachment key.  Example: TESTID')
  parser.add_argument(
      '--start_date', '-s', default=DEFAULT_START_TIME,
      help='The start of date.  Default: %s' % DEFAULT_START_TIME)
  parser.add_argument(
      '--end_date', '-e', default=DEFAULT_END_TIME,
      help='The end of date.  Default: %s' % DEFAULT_END_TIME)
  parser.add_argument(
      '--target_dir', '-t', default=DEFAULT_TARGET_DIR,
      help='The target directory.  Default: %s' % DEFAULT_TARGET_DIR)
  parser.add_argument(
      '--bq_path', '-b', default=DEFAULT_BQ_PATH,
      help='The bq path.  Default: %s' % DEFAULT_BQ_PATH)
  parser.add_argument(
      '--gsutil_path', '-g', default=DEFAULT_GSUTIL_PATH,
      help='The gsutil path.  Default: %s' % DEFAULT_GSUTIL_PATH)
  parser.add_argument(
      '--serial_number_key', '-sn_key', default=DEFAULT_SERIAL_NUMBER_KEY,
      help='The key of the serial number to put in the file name.  '
           'Default: %s' % DEFAULT_SERIAL_NUMBER_KEY)
  parser.add_argument(
      '--serial_number', '-sn', type=str, action='append',
      help='The value of the serial number to download.  This can be added '
           'multiple times.  This feature is implemented by this script '
           'instead of query.')
  args = parser.parse_args()

  CheckVersion(args)

  result_json = RunQuery(args).strip()

  results = json.loads(result_json)
  if args.serial_number:
    results = Filter(args, results)

  if not results:
    print('Query returned zero records.\n'
          'Done!')
    return
  print('Found %d files!\n' % len(results))

  if not os.path.isdir(os.path.join(args.target_dir, 'tmp')):
    os.makedirs(os.path.join(args.target_dir, 'tmp'))

  Download(args, results)
  CopyAndDelete(args, results)

  print('Done!')


if __name__ == '__main__':
  main()
