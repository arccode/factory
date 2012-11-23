# Copyright (c) 2011 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

from xml.dom import minidom

import cherrypy
import json
import os
import time
import urlparse


def _LogMessage(message):
  cherrypy.log(message, 'UPDATE')

def _ChangeUrlPort(url, new_port):
  """Return the URL passed in with a different port"""
  scheme, netloc, path, query, fragment = urlparse.urlsplit(url)
  host_port = netloc.split(':')

  if len(host_port) == 1:
    host_port.append(new_port)
  else:
    host_port[1] = new_port

  print host_port
  netloc = "%s:%s" % tuple(host_port)

  return urlparse.urlunsplit((scheme, netloc, path, query, fragment))


class ServerEngine(object):
  """Class that contains functionality that handles Chrome OS update pings.

  Members:
    factory_config_path: Path to the factory config file if handling factory
      requests.
    static_dir: Path to store installation packages.
    port: port to host miniomaha
    proxy_port: port of local proxy to tell client to connect to you through.
  """

  def __init__(self, static_dir,
               factory_config_path=None,
               port=8080, proxy_port=None,
               *args, **kwargs):
    self.app_id = '87efface-864d-49a5-9bb3-4b050a7c227a'
    self.static_dir = static_dir
    self.factory_config = factory_config_path
    self.proxy_port = proxy_port

    # Initialize empty host info cache. Used to keep track of various bits of
    # information about a given host.
    self.host_info = {}

  def _GetSecondsSinceMidnight(self):
    """Returns the seconds since midnight as a decimal value."""
    now = time.localtime()
    return now[3] * 3600 + now[4] * 60 + now[5]

  def _GetSize(self, update_path):
    """Returns the size of the file given."""
    return os.path.getsize(update_path)

  def _GetHash(self, update_path):
    """Returns the sha1 of the file given."""
    cmd = ('cat %s | openssl sha1 -binary | openssl base64 | tr \'\\n\' \' \';'
           % update_path)
    return os.popen(cmd).read().rstrip()

  def _IsDeltaFormatFile(self, filename):
    try:
      file_handle = open(filename, 'r')
      delta_magic = 'CrAU'
      magic = file_handle.read(len(delta_magic))
      return magic == delta_magic
    except Exception:
      return False

  # TODO(petkov): Consider optimizing getting both SHA-1 and SHA-256 so that
  # it takes advantage of reduced I/O and multiple processors. Something like:
  # % tee < FILE > /dev/null \
  #     >( openssl dgst -sha256 -binary | openssl base64 ) \
  #     >( openssl sha1 -binary | openssl base64 )
  def _GetSHA256(self, update_path):
    """Returns the sha256 of the file given."""
    cmd = ('cat %s | openssl dgst -sha256 -binary | openssl base64' %
           update_path)
    return os.popen(cmd).read().rstrip()

  def _GetMd5(self, update_path):
    """Returns the md5 checksum of the file given."""
    cmd = ("md5sum %s | awk '{print $1}'" % update_path)
    return os.popen(cmd).read().rstrip()

  def GetUpdatePayload(self, hash, sha256, size, url, is_delta_format):
    """Returns a payload to the client corresponding to a new update.

    Args:
      hash: hash of update blob
      sha256: SHA-256 hash of update blob
      size: size of update blob
      url: where to find update blob
    Returns:
      Xml string to be passed back to client.
    """
    delta = 'false'
    if is_delta_format:
      delta = 'true'
    payload = """<?xml version="1.0" encoding="UTF-8"?>
      <gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">
        <daystart elapsed_seconds="%s"/>
        <app appid="{%s}" status="ok">
          <ping status="ok"/>
          <updatecheck
            codebase="%s"
            hash="%s"
            sha256="%s"
            needsadmin="false"
            size="%s"
            IsDelta="%s"
            status="ok"/>
        </app>
      </gupdate>
    """
    return payload % (self._GetSecondsSinceMidnight(),
                      self.app_id, url, hash, sha256, size, delta)

  def GetNoUpdatePayload(self):
    """Returns a payload to the client corresponding to no update."""
    payload = """<?xml version="1.0" encoding="UTF-8"?>
      <gupdate xmlns="http://www.google.com/update2/response" protocol="2.0">
        <daystart elapsed_seconds="%s"/>
        <app appid="{%s}" status="ok">
          <ping status="ok"/>
          <updatecheck status="noupdate"/>
        </app>
      </gupdate>
    """
    return payload % (self._GetSecondsSinceMidnight(), self.app_id)

  def ImportFactoryConfigFile(self, filename, validate_checksums=False):
    """Imports a factory-floor server configuration file. The file should
    be in this format:
      config = [
        {
          'qual_ids': set([1, 2, 3, "x86-generic"]),
          'factory_image': 'generic-factory.gz',
          'factory_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'release_image': 'generic-release.gz',
          'release_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'oempartitionimg_image': 'generic-oem.gz',
          'oempartitionimg_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'efipartitionimg_image': 'generic-efi.gz',
          'efipartitionimg_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'stateimg_image': 'generic-state.gz',
          'stateimg_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'firmware_image': 'generic-firmware.gz',
          'firmware_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
        },
        {
          'qual_ids': set([6]),
          'factory_image': '6-factory.gz',
          'factory_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'release_image': '6-release.gz',
          'release_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'oempartitionimg_image': '6-oem.gz',
          'oempartitionimg_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'efipartitionimg_image': '6-efi.gz',
          'efipartitionimg_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'stateimg_image': '6-state.gz',
          'stateimg_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
          'firmware_image': '6-firmware.gz',
          'firmware_checksum': 'AtiI8B64agHVN+yeBAyiNMX3+HM=',
        },
      ]
    The server will look for the files by name in the static files
    directory.

    If validate_checksums is True, validates checksums and exits. If
    a checksum mismatch is found, it's printed to the screen.
    """
    f = open(filename, 'r')
    output = {}
    exec(f.read(), output)
    self.factory_config = output['config']
    success = True
    for stanza in self.factory_config:
      for key in stanza.copy().iterkeys():
        suffix = '_image'
        if key.endswith(suffix):
          kind = key[:-len(suffix)]
          stanza[kind + '_size'] = self._GetSize(os.path.join(
              self.static_dir, stanza[kind + '_image']))
          if validate_checksums:
            factory_checksum = self._GetHash(os.path.join(self.static_dir,
                                             stanza[kind + '_image']))
            if factory_checksum != stanza[kind + '_checksum']:
              print ('Error: checksum mismatch for %s. Expected "%s" but file '
                     'has checksum "%s".' % (stanza[kind + '_image'],
                                             stanza[kind + '_checksum'],
                                             factory_checksum))
              success = False

    if validate_checksums:
      if success is False:
        raise Exception('Checksum mismatch in conf file.')

      print 'Config file looks good.'

  def GetFactoryImage(self, board_id, channel):
    kind = channel.rsplit('-', 1)[0]
    for stanza in self.factory_config:
      if board_id not in stanza['qual_ids']:
        continue
      if kind + '_image' not in stanza:
        break
      return (stanza[kind + '_image'],
              stanza[kind + '_checksum'],
              stanza[kind + '_size'])
    return (None, None, None)

  def HandleFactoryRequest(self, board_id, channel):
    (filename, checksum, size) = self.GetFactoryImage(board_id, channel)
    if filename is None:
      _LogMessage('unable to find image for board %s' % board_id)
      return self.GetNoUpdatePayload()
    url = '%s/static/%s' % (self.hostname, filename)
    is_delta_format = self._IsDeltaFormatFile(filename)
    _LogMessage('returning update payload ' + url)
    # Factory install is using memento updater which is using the sha-1 hash so
    # setting sha-256 to an empty string.
    return self.GetUpdatePayload(checksum, '', size, url, is_delta_format)

  def HandleUpdatePing(self, data, label=None):
    """Handles an update ping from an update client.

    Args:
      data: xml blob from client.
      label: optional label for the update.
    Returns:
      Update payload message for client.
    """
    # Set hostname as the hostname that the client is calling to and set up
    # the url base.
    self.hostname = cherrypy.request.base
    static_urlbase = '%s/static' % self.hostname

    # If we have a proxy port, adjust the URL we instruct the client to
    # use to go through the proxy.
    if self.proxy_port:
      static_urlbase = _ChangeUrlPort(static_urlbase, self.proxy_port)

    _LogMessage('Using static url base %s' % static_urlbase)
    _LogMessage('Handling update ping as %s: %s' % (self.hostname, data))

    update_dom = minidom.parseString(data)
    root = update_dom.firstChild

    # Determine request IP, strip any IPv6 data for simplicity.
    client_ip = cherrypy.request.remote.ip.split(':')[-1]

    # Initialize host info dictionary for this client if it doesn't exist.
    self.host_info.setdefault(client_ip, {})

    # Store event details in the host info dictionary for API usage.
    event = root.getElementsByTagName('o:event')
    if event:
      self.host_info[client_ip]['last_event_status'] = (
          int(event[0].getAttribute('eventresult')))
      self.host_info[client_ip]['last_event_type'] = (
          int(event[0].getAttribute('eventtype')))

    # We only generate update payloads for updatecheck requests.
    update_check = root.getElementsByTagName('o:updatecheck')
    if not update_check:
      _LogMessage('Non-update check received.  Returning blank payload.')
      # TODO(sosa): Generate correct non-updatecheck payload to better test
      # update clients.
      return self.GetNoUpdatePayload()

    # Since this is an updatecheck, get information about the requester.
    query = root.getElementsByTagName('o:app')[0]
    client_version = query.getAttribute('version')
    channel = query.getAttribute('track')
    board_id = (query.hasAttribute('board') and query.getAttribute('board')
                or 'unknown')

    # Store version for this host in the cache.
    self.host_info[client_ip]['last_known_version'] = client_version

    # Check if an update has been forced for this client.
    forced_update = self.host_info[client_ip].pop('forced_update_label', None)
    if forced_update:
      label = forced_update

    return self.HandleFactoryRequest(board_id, channel)

  def HandleHostInfoPing(self, ip):
    """Returns host info dictionary for the given IP in JSON format."""
    assert ip, 'No ip provided.'
    if ip in self.host_info:
      return json.dumps(self.host_info[ip])

  def HandleSetUpdatePing(self, ip, label):
    """Sets forced_update_label for a given host."""
    assert ip, 'No ip provided.'
    assert label, 'No label provided.'
    self.host_info.setdefault(ip, {})['forced_update_label'] = label
