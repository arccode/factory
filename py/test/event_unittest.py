#!/usr/bin/env python2
# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import json
import threading
import time
import unittest

import factory_common  # pylint: disable=unused-import
from cros.factory.test import event
from cros.factory.utils import net_utils
from cros.factory.utils import process_utils


EventType = event.Event.Type

PING = 'PING'
PONG = 'PONG'


class EventTest(unittest.TestCase):
  def testConvertJSON(self):
    event1 = event.Event(EventType.SET_HTML, html='abc')
    event1_json = event1.to_json()

    event2 = event.Event.from_json(event1_json)
    event2_json = event2.to_json()

    self.assertEqual(event1, event2)

    event1_dict = json.loads(event1_json)
    event2_dict = json.loads(event2_json)
    self.assertEqual(event1_dict, event2_dict)


# We add an additional layer of class, so the unittest TestCase finder won't
# find the base class EventServerClientTest.
class Tests(object):
  class EventServerClientTestBase(unittest.TestCase):
    has_pong_client = True

    def setUp(self):
      self.server = event.EventServer()
      self.server_thread = process_utils.StartDaemonThread(
          target=self.server.serve_forever)
      self.clients = []

      if self.has_pong_client:
        self.pong_client = event.ThreadingEventClient(callback=self._Pong)
        self.clients.append(self.pong_client)

    def CreateClient(self, callback=None):
      # pylint: disable=no-member
      if callback is None:
        callback = lambda unused_event: None
      client = self.client_class(callback=callback)
      self.clients.append(client)
      return client

    def _Pong(self, ev):
      if ev.type == PING:
        self.pong_client.post_event(event.Event(PONG, msg=ev.msg))

    def tearDown(self):
      for client in self.clients:
        client.close()

      net_utils.ShutdownTCPServer(self.server)
      self.server_thread.join()
      self.server.server_close()

      # Make sure we're not leaving any extra threads hanging around after a
      # second.
      extra_threads = [t for t in threading.enumerate()
                       if t != threading.current_thread()]
      end_time = time.time() + 1
      for thread in extra_threads:
        thread.join(timeout=end_time - time.time())
        self.assertFalse(thread.isAlive(),
                         "Thread %r still alive after 1 second." % thread)

  class EventServerClientTest(EventServerClientTestBase):
    def testBasic(self):
      # pylint: disable=unnecessary-lambda
      client_events = []
      pong_got = threading.Event()
      def _Callback(ev):
        client_events.append(ev)
        if ev.type == PONG:
          pong_got.set()
      client = self.CreateClient(_Callback)

      ev = event.Event(PING, msg='msg')
      pong_msg = client.request_response(ev, lambda ev: ev.type == PONG)
      self.assertEqual(PONG, pong_msg.type)
      self.assertEqual('msg', pong_msg.msg)

      pong_got.wait()
      self.assertEqual(client_events, [ev, pong_msg])

    def testTimeout(self):
      client = self.CreateClient()
      self.assertIsNone(client.wait(lambda ev: ev.type == PONG, timeout=0.1))


class EventServerBlockingClientTest(Tests.EventServerClientTest):
  client_class = event.BlockingEventClient


class EventServerThreadingClientTest(Tests.EventServerClientTest):
  client_class = event.ThreadingEventClient


class EventUtilityFunctionTest(Tests.EventServerClientTestBase):
  client_class = event.BlockingEventClient

  def testPostEvent(self):
    client = self.CreateClient()
    event.PostEvent(event.Event(PING, msg='msg'))
    pong_msg = client.wait(lambda ev: ev.type == PONG)
    self.assertEqual(PONG, pong_msg.type)
    self.assertEqual('msg', pong_msg.msg)

  def testPostNewEvent(self):
    client = self.CreateClient()
    event.PostNewEvent(PING, msg='msg')
    pong_msg = client.wait(lambda ev: ev.type == PONG)
    self.assertEqual(PONG, pong_msg.type)
    self.assertEqual('msg', pong_msg.msg)

  def testSendEvent(self):
    pong_msg = event.SendEvent(
        event.Event(PING, msg='msg'), lambda ev: ev.type == PONG)
    self.assertEqual(PONG, pong_msg.type)
    self.assertEqual('msg', pong_msg.msg)


class EventServerQueueCleanTest(Tests.EventServerClientTestBase):
  client_class = event.BlockingEventClient
  has_pong_client = False

  def testQueueClean(self):
    client = self.CreateClient()
    for unused_i in range(1000):
      client.post_event(event.Event(PING, msg='msg'))
    client.post_event(event.Event(PONG, msg='msg'))
    client.wait(lambda ev: ev.type == PONG)

    # pylint: disable=protected-access
    with self.server._lock:
      for queue in self.server._queues:
        self.assertFalse(queue.qsize())


if __name__ == '__main__':
  unittest.main()
