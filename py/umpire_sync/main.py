#!/usr/bin/env python3
#
# Copyright 2021 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.
"""Update bundles of secondary Umpires on a regular basis."""

import argparse
import logging
import socket
import time
import xmlrpc.client

from cros.factory.umpire_sync import utils
from cros.factory.utils import net_utils


RPC_PORT_OFFSET = 2
RPC_TIMEOUT = 1
UPDATE_TIMEOUT = 600


class PrimaryUmpire:

  def __init__(self, host, port):
    self.rpc_url = 'http://%s:%d' % (host, port + RPC_PORT_OFFSET)
    self.url = 'http://%s:%d' % (host, port)
    self.proxy = xmlrpc.client.ServerProxy(self.rpc_url)
    self.active_payload = self.GetActivePayload()

  def CheckPayloadUpdate(self):
    new_payload = self.GetActivePayload()
    if new_payload != self.active_payload:
      self.active_payload = new_payload
      return True
    return False

  def GetActivePayload(self):
    try:
      payload = self.proxy.GetActivePayload()
      return payload
    except Exception as e:
      logging.error(
          'Failed to get the active bundle from the primary umpire[%s]: %s',
          self.rpc_url, e)


class SecondaryUmpire:

  def __init__(self, urls, status_path):
    self.proxies = []
    self.check_alive_proxies = []
    self.urls = urls
    self.status = utils.StatusUpdater(status_path)

    for url in urls:
      self.status.SetStatus(url, utils.STATUS.Waiting)
      host, port = url.split('//')[1].split(':')[0], int(url.split(':')[2])
      rpc_url = 'http://%s:%d' % (host, port + RPC_PORT_OFFSET)
      self.proxies.append(self._MakeTimeoutProxy(rpc_url, UPDATE_TIMEOUT))
      self.check_alive_proxies.append(
          self._MakeTimeoutProxy(rpc_url, RPC_TIMEOUT))

  def _MakeTimeoutProxy(self, rpc_url, timeout):
    return net_utils.TimeoutXMLRPCServerProxy(rpc_url, timeout=timeout,
                                              allow_none=True)

  def SynchronizeBundle(self, primary_payload, primary_url):
    for check_alive_proxy, proxy, url in zip(self.check_alive_proxies,
                                             self.proxies, self.urls):
      try:
        # Check the secondary xmlrpc server is alive in timeout seconds
        check_alive_proxy.GetVersion()
        self.status.SetStatus(url, utils.STATUS.Updating)
        sync_status = proxy.CheckAndUpdate(primary_payload, primary_url)
        if sync_status:
          self.status.SetStatus(url, utils.STATUS.Success,
                                time.strftime('%Y-%m-%d %H:%M:%S'))
          logging.info('Update Successfully.')
        else:
          self.status.SetStatus(url, utils.STATUS.Success)
      except Exception as e:
        self.status.SetStatus(url, utils.STATUS.Failure)
        logging.error('Failed to update the secondary umpire[%s]: %s', url, e)

  def WaitToSynchronize(self):
    for url in self.urls:
      self.status.SetStatus(url, utils.STATUS.Waiting)


def _ParseArguments():
  parser = argparse.ArgumentParser()

  parser.add_argument('-l', '--log_path',
                      help='path to the log file of the Umpire sync service')
  parser.add_argument('-s', '--status_file_path',
                      help="path to secondary umpires' updating status file")
  parser.add_argument('--primary_port',
                      help='the inside port of the primary umpire', type=int,
                      default=8080)
  parser.add_argument('-p', '--primary_url', help='the url of primary umpire')
  parser.add_argument('-t', '--sync_time', help='the period to synchronize',
                      type=int, default=60)
  parser.add_argument('--secondary_urls', help='the url of secondary umpires',
                      nargs='*', default=[])

  return parser.parse_args()


def main():
  args = _ParseArguments()
  logging.basicConfig(filename=args.log_path, level=logging.INFO)

  # The `private_primary_host` is the private IP of the primary Umpire for the
  # service itself, while `args.primary_url` is the public IP for the secondary
  # Umpires.
  private_primary_host = socket.gethostbyname(socket.gethostname())
  primary_umpire = PrimaryUmpire(private_primary_host, args.primary_port)
  secondary_umpires = SecondaryUmpire(args.secondary_urls,
                                      args.status_file_path)

  while True:
    if primary_umpire.CheckPayloadUpdate():
      secondary_umpires.WaitToSynchronize()
    primary_payload = primary_umpire.GetActivePayload()
    secondary_umpires.SynchronizeBundle(primary_payload, args.primary_url)
    time.sleep(args.sync_time)


if __name__ == '__main__':
  main()
