#!/usr/bin/python
#
# Copyright (c) 2014 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import os
import shutil
import tempfile
import unittest

import factory_common  # pylint: disable=W0611
from cros.factory.umpire import common
from cros.factory.umpire import config as umpire_config
from cros.factory.umpire.service import http
from cros.factory.umpire.service import indent_text_writer
from cros.factory.umpire import umpire_env
from cros.factory.utils import file_utils


class TestLightyConfigWriter(unittest.TestCase):

  def setUp(self):
    self.writer = indent_text_writer.IndentTextWriter(indent_first_line=False)

  def testLightyAuto(self):
    self.assertEqual('123',
                     http.LightyConfigWriter.LightyAuto(123, self.writer))
    self.assertEqual('"string"',
                     http.LightyConfigWriter.LightyAuto('string', self.writer))
    self.assertEqual(
        '(\n'
        '  "k" => "v",\n'
        ')',
        http.LightyConfigWriter.LightyAuto({'k': 'v'}, self.writer))
    self.assertEqual(
        '(\n'
        '  "item 1",\n'
        '  "item 2",\n'
        ')',
        http.LightyConfigWriter.LightyAuto(['item 1', 'item 2'], self.writer))

  def testLightyBlock(self):
    self.assertEqual(
        '{\n'
        '  k = (\n'
        '    "innerK" => "v",\n'
        '  ),\n'
        '}',
        http.LightyConfigWriter.LightyBlock({'k': {'innerK': 'v'}},
                                            self.writer))

  def testLightyTopBlock(self):
    self.assertEqual(
        'k1 = 123\n'
        'k2 = "v2"',
        http.LightyConfigWriter.LightyBlock({'k1': 123, 'k2': 'v2'},
                                            self.writer, top_block=True))
    self.assertEqual(
        'k = (\n'
        '  "innerK" => "v",\n'
        ')',
        http.LightyConfigWriter.LightyBlock({'k': {'innerK': 'v'}},
                                            self.writer, top_block=True))

    self.assertEqual(
        '$SERVER["socket"] == ":8080" {\n}',
        http.LightyConfigWriter.LightyBlock(
            {http.LightyConditional('$SERVER["socket"] == ":8080"'): {}},
            self.writer, top_block=True))

    # After a http.LightyConditional is always a LightyBlock.
    self.assertEqual(
        'dummy_cond == True {\n'
        '  k = "v",\n'
        '}',
        http.LightyConfigWriter.LightyBlock(
            {http.LightyConditional('dummy_cond == True'): {'k': 'v'}},
            self.writer, top_block=True))

  def testWrite(self):
    with file_utils.UnopenedTemporaryFile() as temp_file:
      writer = http.LightyConfigWriter(temp_file)
      writer.Write({'server.bind': '0.0.0.0',
                    'server.port': 8080,
                    'index-file.names': ['index.html']})
      writer.Close()
      self.assertEqual(
          'index-file.names = (\n'
          '  "index.html",\n'
          ')\n'
          'server.bind = "0.0.0.0"\n'
          'server.port = 8080\n',
          file_utils.ReadFile(temp_file))


class TestHTTPService(unittest.TestCase):

  def setUp(self):
    self.env = umpire_env.UmpireEnv()
    self.temp_dir = tempfile.mkdtemp()
    self.env.base_dir = self.temp_dir
    os.makedirs(self.env.config_dir)

  def tearDown(self):
    if os.path.isdir(self.temp_dir):
      shutil.rmtree(self.temp_dir)

  def testGenerateLightyConfig(self):
    umpire_ip = '10.0.0.1'
    umpire_port = 9001
    umpire_config_dict = {
        'ip': umpire_ip,
        'port': umpire_port,
        'services': {'http': {
            'reverse_proxies': [
                {'remoteip': '192.168.51.0/24',
                 'proxy_addr': '192.168.51.1:8080'},
                {'remoteip': '192.168.52.0/24',
                 'proxy_addr': '192.168.52.1:8080'}]}},
        'bundles': [{
            'id': 'default',
            'note': '',
            'shop_floor': {'handler': ''},
            'resources': {
                'device_factory_toolkit': '',
                'stateful_partition': '',
                'oem_partition': '',
                'rootfs_release': '',
                'rootfs_test': ''}}],
        'rulesets': [{
            'bundle_id': 'default',
            'note': '',
            'active': True}]}
    self.env.config = umpire_config.UmpireConfig(umpire_config_dict)
    config_path = http.HTTPService.GenerateLightyConfig(
        umpire_config_dict, self.env)

    self.assertRegexpMatches(
        config_path,
        os.path.join(
            self.env.config_dir,
            'lighttpd_#[0-9a-f]{%d}#.conf' % common.RESOURCE_HASH_DIGITS))

    # Store the output lighttpd.conf file into config (list).
    # Also make a dict (line => line number) to speed up line and line block
    # matching.
    config = [s.rstrip() for s in file_utils.ReadLines(config_path)]
    config_first_occur_line = {}
    for i, line in enumerate(config):
      if line not in config_first_occur_line:
        config_first_occur_line[line] = i

    def ExpectLine(line):
      self.assertIn(line, config_first_occur_line)

    def ExpectLines(expect_lines):
      # Try matching first line.
      self.assertIn(expect_lines[0], config_first_occur_line)
      # Get the second line number and compare the following lines.
      line_num = config_first_occur_line[expect_lines.pop(0)] + 1
      for expect in expect_lines:
        self.assertTrue(line_num < len(config))
        self.assertEqual(expect, config[line_num])
        line_num += 1

    ExpectLine('server.bind = "%s"' % '0.0.0.0')
    ExpectLine('server.port = %d' % umpire_port)

    base_dir = self.env.base_dir
    ExpectLine('accesslog.filename = "%s/log/httpd_access.log"' % base_dir)
    ExpectLine('server.errorlog = "%s/log/httpd_error.log"' % base_dir)
    ExpectLine('server.pid-file = "%s/run/httpd.pid"' % base_dir)

    expect_fastcgi_conf = ['fastcgi.server = (']
    fcgi_port = self.env.fastcgi_start_port
    for p in xrange(fcgi_port,
                    fcgi_port + umpire_config.NUMBER_SHOP_FLOOR_HANDLERS):
      expect_fastcgi_conf.extend([
          '  "/shop_floor/%d/" => (' % p,
          '    (',
          '      "check-local" => "disable",',
          '      "host" => "127.0.0.1",',
          '      "port" => %d,' % p,
          '    ),',
          '  ),'])
    expect_fastcgi_conf.append(')')
    ExpectLines(expect_fastcgi_conf)

    ExpectLines([
        '$HTTP["remoteip"] == "192.168.51.0/24" {',
        '  url.redirect = (',
        '    "^/res/(.*)" => "http://192.168.51.1:8080/res/$1",',
        '  ),',
        '}',
        '$HTTP["remoteip"] == "192.168.52.0/24" {',
        '  url.redirect = (',
        '    "^/res/(.*)" => "http://192.168.52.1:8080/res/$1",',
        '  ),',
        '}'])


if __name__ == '__main__':
  unittest.main()
