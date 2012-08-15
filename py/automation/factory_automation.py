#!/usr/bin/python -u
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

'''Factory Automation Script
Automatically run and control factory tests.
'''

import ast
import imp
import logging
import os
import sys
import time

import factory_common  # pylint: disable=W0611
from cros.factory.test import state
from cros.factory.test.event import Event, EventClient

# pylint: disable=F0401
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
# pylint: enable=F0401

from ectool_command import ECToolCommand


AUTOMATION_DIR = os.path.dirname(__file__)
DEFAULT_RESPONSE_TIMEOUT = 10  # secs
POLL_FREQUENCY = 0.5  # sec


class FactoryAutomation(object):
  '''
  Properties:
    is_pending_shutdown: true or false.
      Event client callback will modify this.
      If true, since the system is shutting down (in RebootStep),
      main function should stop executing.
    enable_callback: true or false.
      Callback starts when initialization finishes.
    event_client: event_client to communicate with factory.
    rpc_client: rpc_client to communicate with factory.
    test_list: the full list of tests, which contains information of tests.
    is_shutdown_test: a map from test_path to boolean.
      It tells whether this test is a shutdown test (including reboot).
    is_leaf: a map from test_path to boolean, telling whether it is leaf test.
    driver: the selenium webdriver, used to control chrome browser.
    path_nodeid_map: a map from test_path to its html element id.
      It is obtained from goofy.js. Used while we want to click the test.
    ectool_command: the object used to send "ectool ..." commands
    config: the instruction about how to automate the tests. Read from a file
  '''

  def __init__(self):
    self.is_pending_shutdown = False
    self.enable_callback = False
    self.event_client = None
    self.rpc_client = None

    self.test_list = None
    self.is_shutdown_test = None
    self.is_leaf = None

    self.driver = None
    self.path_nodeid_map = None
    self.ectool_command = None

    self.config = None

    logging.basicConfig(
      format=('[%(levelname)s] ' +
              ' %(filename)s:%(lineno)d %(asctime)s.%(msecs)03d %(message)s'),
      level=logging.INFO,
      datefmt='%Y-%m-%d %H:%M:%S')

  def CreateTestProperty(self, test):
    self.is_shutdown_test[test['path']] = test['is_shutdown_step']
    if len(test['subtests']) == 0:
      self.is_leaf[test['path']] = True
    else:
      self.is_leaf[test['path']] = False
    for subtest in test['subtests']:
      self.CreateTestProperty(subtest)

  def Init(self, chrome_binary_path, chrome_option_list, factory_url):
    def HandleEvent(event):
      if event.type == Event.Type.PENDING_SHUTDOWN:
        self.is_pending_shutdown = True
        return
      # Wait for the main program
      while not self.enable_callback:
        time.sleep(POLL_FREQUENCY)
        continue
      if (event.type == Event.Type.STATE_CHANGE and
          event.state.status == 'ACTIVE'):
        self.AutomateTest(event.path)

    self.event_client = EventClient(callback=HandleEvent)
    self.rpc_client = state.get_instance()

    self.test_list = self.rpc_client.get_test_list()
    self.is_shutdown_test = {}
    self.is_leaf = {}
    self.CreateTestProperty(self.test_list)

    # To run chrome in factory image,
    # please also ensure chromedriver is in the path and DISPLAY=:0
    # Now set up options in order to open chrome in factory image
    options = ChromeOptions()
    options.binary_location = chrome_binary_path
    for option in chrome_option_list:
      options.add_argument(option)

    # Initialize the driver, and it will start chromedriver and chrome browser
    self.driver = webdriver.Chrome(chrome_options=options)
    # Go to factory url
    self.driver.get(factory_url)
    self.driver.implicitly_wait(DEFAULT_RESPONSE_TIMEOUT)

    # Make sure chrome has loaded the page
    self.driver.find_element_by_id('goofy-logo-text')
    time.sleep(2)

    # Get path_nodeid_map from goofy.js
    script = 'return window.goofy.pathNodeIdMap'
    self.path_nodeid_map = self.driver.execute_script(script)

    # Get the instruction about how to do the automation
    config_path = os.path.join(AUTOMATION_DIR, 'automation.config')
    self.config = ast.literal_eval(file(config_path).read())

    self.ectool_command = ECToolCommand()

  def GetStatus(self, test_path):
    return self.rpc_client.get_test_state(test_path).status

  def ExpandAll(self):
    '''
    Expand all expandable elements.
    '''
    class_name = 'goog-tree-expand-icon-plus'
    a_list = self.driver.find_elements_by_class_name(class_name)
    for element in a_list:
      element.click()

  def ClickPopup(self, element, nth_popup):
    '''
    Click the element. A popup (goog-menu) should appear.
    Then, click the nth_popup.

    @param element: The element to be clicked.
    @param nth_popup: The number of the popup to be clicked. Starting from 0.
    '''
    element.click()
    popup = self.driver.find_elements_by_class_name('goog-menuitem')
    popup[nth_popup].click()

  def WaitTestStatus(self, test_path, status_check, time_out=None):
    '''
    Wait for the test until the status check is satisfied
    Return True if see the status, False if timeout
    '''
    if time_out:
      end_time = time.time() + time_out
    while True:
      status = self.GetStatus(test_path)
      if status_check(status):
        return True
      time.sleep(POLL_FREQUENCY)
      if time_out and time.time() > end_time:
        logging.warning('Wait %s reaches time out (%s sec). '
                        'Give up waiting.', test_path, time_out)
        return False

  def StopTest(self, test_path, mark_fail):
    '''
    @param test_path: The path of the test we want to stop
    @param mark_fail: Whether we want to mark the test fail after stop it.
      Invalid for shutdown step.
    '''
    # For a shutdown step, we need special way to stop it
    if self.is_shutdown_test[test_path]:
      event = Event(Event.Type.CANCEL_SHUTDOWN)
    else:
      event = Event(Event.Type.STOP, path=test_path, fail=mark_fail)
    self.event_client.post_event(event)

  def ControlTest(self, test_path, time_out=None, string_for_browser=None,
                  keys_for_ec=None, custom_function=None):
    '''
    Press the input_keys, and kill the test after timeout.
    There are three ways to send inputs:
      string_for_browser: the string will be sent to chrome browser.
      keys_for_ec: press these keys using "ectool ..." command.
      custom_function: the name of the user defined program.
    If all three ways are specified, they will be executed sequentially
    '''
    if string_for_browser is not None:
      test_window = self.driver.find_element_by_class_name('goofy-test-iframe')
      test_window.send_keys(string_for_browser)
    if keys_for_ec is not None:
      self.ectool_command.PressString(keys_for_ec)
    if custom_function is not None:
      custom_function = imp.load_source('custom_function',
                                        '%s/custom_function/%s.py' %
                                        (AUTOMATION_DIR, custom_function))
      custom_function.Main(self, test_path)

    if time_out:
      status_check = lambda status: status != 'ACTIVE'
      has_finished = self.WaitTestStatus(test_path, status_check, time_out)
      if not has_finished:
        self.StopTest(test_path, True)

  def AutomateTest(self, test_path):
    '''
    This function is called whenever a test is running.
    '''
    if self.GetStatus(test_path) != 'ACTIVE': # Make sure still active
      return
    if not self.is_leaf[test_path]:
      return
    # Need to wait a bit to make sure the test starts
    # (to stop tests and for gtk)
    time.sleep(2)
    if not test_path in self.config:
      logging.warning('"%s" not in config. Stop it.', test_path)
      self.StopTest(test_path, False)
      return
    logging.info('Automate "%s" from status %s.',
                 test_path, self.GetStatus(test_path))
    self.ControlTest(test_path, *self.config[test_path])

  def Main(self, argv):
    '''
    Main function of automation.
    Args:
      chrome_binary_path
      chrome_option_1
      chrome_option_2
      ...
      chrome_option_n
      factory_url
    '''
    # Map main argument into init argument
    chrome_binary_path = argv[1]
    chrome_option_list = argv[2:-1]
    factory_url = argv[-1]

    self.Init(chrome_binary_path, chrome_option_list, factory_url)

    # If within the RebootStep, don't do anything
    if self.is_pending_shutdown:
      logging.info('Just rebooted. Waiting for the next reboot.')
      return 0

    # Expand all elements, so we can click them
    self.ExpandAll()

    # Make callback starts working
    self.enable_callback = True

    logging.info('Reach the end of automation script.')
    # Should never quit
    while True:
      time.sleep(10)

if __name__ == '__main__':
  FactoryAutomation().Main(sys.argv)
