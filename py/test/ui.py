#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2012 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.


# DESCRIPTION :
#
# This library provides convenience routines to launch factory tests.
# This includes support for drawing the test widget in a window at the
# proper location, grabbing control of the mouse, and making the mouse
# cursor disappear.
#
# This UI is intended to be used by the factory autotest suite to
# provide factory operators feedback on test status and control over
# execution order.
#
# In short, the UI is composed of a 'console' panel on the bottom of
# the screen which displays the autotest log, and there is also a
# 'test list' panel on the right hand side of the screen. The
# majority of the screen is dedicated to tests, which are executed in
# seperate processes, but instructed to display their own UIs in this
# dedicated area whenever possible. Tests in the test list are
# executed in order by default, but can be activated on demand via
# associated keyboard shortcuts. As tests are run, their status is
# color-indicated to the operator -- greyed out means untested, yellow
# means active, green passed and red failed.

import logging
import os
import re
import string
import subprocess
import sys
import threading
import time
from itertools import count, izip, product
from optparse import OptionParser

# GTK and X modules
import gobject
import gtk
import pango

# Guard loading Xlib because it is currently not available in the
# image build process host-depends list. Failure to load in
# production should always manifest during regular use.
try:
  from Xlib import X
  from Xlib.display import Display
except:
  pass

# Factory and autotest modules
import factory_common # pylint: disable=W0611
from cros.factory.test import factory
from cros.factory.test.factory import TestState
from cros.factory.test.test_ui import FactoryTestFailure
from cros.factory.test.event import Event, EventClient
from cros.factory.utils import debug_utils


# For compatibility with tests before TestState existed
ACTIVE = TestState.ACTIVE
PASSED = TestState.PASSED
FAILED = TestState.FAILED
UNTESTED = TestState.UNTESTED

# Arrow symbols
SYMBOL_RIGHT_ARROW = u'\u25b8'
SYMBOL_DOWN_ARROW = u'\u25bc'

# Color definition
BLACK = gtk.gdk.Color()
RED =  gtk.gdk.Color(0xFFFF, 0, 0)
GREEN = gtk.gdk.Color(0, 0xFFFF, 0)
BLUE = gtk.gdk.Color(0, 0, 0xFFFF)
WHITE = gtk.gdk.Color(0xFFFF, 0xFFFF, 0xFFFF)
LIGHT_GREEN = gtk.gdk.color_parse('light green')
SEP_COLOR = gtk.gdk.color_parse('grey50')

RGBA_GREEN_OVERLAY = (0, 0.5, 0, 0.6)
RGBA_YELLOW_OVERLAY = (0.6, 0.6, 0, 0.6)
RGBA_RED_OVERLAY = (0.5, 0, 0, 0.6)

LABEL_COLORS = {
  TestState.ACTIVE: gtk.gdk.color_parse('light goldenrod'),
  TestState.PASSED: gtk.gdk.color_parse('pale green'),
  TestState.FAILED: gtk.gdk.color_parse('tomato'),
  TestState.UNTESTED: gtk.gdk.color_parse('dark slate grey')}

LABEL_FONT = pango.FontDescription('courier new condensed 16')
LABEL_LARGE_FONT = pango.FontDescription('courier new condensed 24')

FAIL_TIMEOUT = 60

MESSAGE_NO_ACTIVE_TESTS = (
    "No more tests to run. To re-run items, press shortcuts\n"
    "from the test list in right side or from following list:\n\n"
    "Ctrl-Alt-A (Auto-Run):\n"
    " Test remaining untested items.\n\n"
    "Ctrl-Alt-F (Re-run Failed):\n"
    " Re-test failed items.\n\n"
    "Ctrl-Alt-R (Reset):\n"
    " Re-test everything.\n\n"
    "Ctrl-Alt-Z (Information):\n"
    " Review test results and information.\n\n"
    )

USER_PASS_FAIL_SELECT_STR = (
  'hit TAB to fail and ENTER to pass\n' +
  '错误请按 TAB，成功请按 ENTER')
# Resolution where original UI is designed for.
_UI_SCREEN_WIDTH = 1280
_UI_SCREEN_HEIGHT = 800

_LABEL_STATUS_ROW_SIZE = (300, 30)
_LABEL_EN_SIZE = (170, 35)
_LABEL_ZH_SIZE = (70, 35)
_LABEL_EN_FONT = pango.FontDescription('courier new extra-condensed 16')
_LABEL_ZH_FONT = pango.FontDescription('normal 12')
_LABEL_T_SIZE = (40, 35)
_LABEL_T_FONT = pango.FontDescription('arial ultra-condensed 10')
_LABEL_UNTESTED_FG = gtk.gdk.color_parse('grey40')
_LABEL_TROUGH_COLOR = gtk.gdk.color_parse('grey20')
_LABEL_STATUS_SIZE = (140, 30)
_LABEL_STATUS_FONT = pango.FontDescription(
  'courier new bold extra-condensed 16')
_OTHER_LABEL_FONT = pango.FontDescription('courier new condensed 20')

_NO_ACTIVE_TEST_DELAY_MS = 500

GLOBAL_HOT_KEY_EVENTS = {
  'r': Event.Type.RESTART_TESTS,
  'a': Event.Type.AUTO_RUN,
  'f': Event.Type.RE_RUN_FAILED,
  'z': Event.Type.REVIEW,
  }
try:
  # Works only if X is available.
  GLOBAL_HOT_KEY_MASK = X.ControlMask | X.Mod1Mask
except:
  pass

# ---------------------------------------------------------------------------
# Client Library


# TODO(hungte) Replace gtk_lock by gtk.gdk.lock when it's availble (need pygtk
# 2.2x, and we're now pinned by 2.1x)
class _GtkLock(object):
  __enter__ = gtk.gdk.threads_enter
  def __exit__(*ignored):
    gtk.gdk.threads_leave()


gtk_lock = _GtkLock()


def make_label(message, font=LABEL_FONT, fg=LIGHT_GREEN,
        size=None, alignment=None):
  """Returns a label widget.

  A wrapper for gtk.Label. The unit of size is pixels under resolution
  _UI_SCREEN_WIDTH*_UI_SCREEN_HEIGHT.

  @param message: A string to be displayed.
  @param font: Font descriptor for the label.
  @param fg: Foreground color.
  @param size: Minimum size for this label.
  @param alignment: Alignment setting.
  @return: A label widget.
  """
  l = gtk.Label(message)
  l.modify_font(font)
  l.modify_fg(gtk.STATE_NORMAL, fg)
  if size:
    # Convert size according to the current resolution.
    l.set_size_request(*convert_pixels(size))
  if alignment:
    l.set_alignment(*alignment)
  return l


def make_status_row(init_prompt,
          init_status,
          label_size=_LABEL_STATUS_ROW_SIZE,
          is_standard_status=True):
  """Returns a widget that live updates prompt and status in a row.

  Args:
    init_prompt: The prompt label text.
    init_status: The status label text.
    label_size: The desired size of the prompt label and the status label.
    is_standard_status: True to interpret status by the values defined by
      LABEL_COLORS, and render text by corresponding color. False to
      display arbitrary text without changing text color.

  Returns:
    1) A dict whose content is linked by the widget.
    2) A widget to render dict content in "prompt:  status" format.
  """
  display_dict = {}
  display_dict['prompt'] = init_prompt
  display_dict['status'] = init_status
  display_dict['is_standard_status'] = is_standard_status

  def prompt_label_expose(widget, event):
    prompt = display_dict['prompt']
    widget.set_text(prompt)

  def status_label_expose(widget, event):
    status = display_dict['status']
    widget.set_text(status)
    if is_standard_status:
      widget.modify_fg(gtk.STATE_NORMAL, LABEL_COLORS[status])

  prompt_label = make_label(
      init_prompt, size=label_size,
      alignment=(0, 0.5))
  delimiter_label = make_label(':', alignment=(0, 0.5))
  status_label = make_label(
      init_status, size=label_size,
      alignment=(0, 0.5))

  widget = gtk.HBox()
  widget.pack_end(status_label, False, False)
  widget.pack_end(delimiter_label, False, False)
  widget.pack_end(prompt_label, False, False)

  status_label.connect('expose_event', status_label_expose)
  prompt_label.connect('expose_event', prompt_label_expose)
  return display_dict, widget


def convert_pixels(size):
  """Converts a pair in pixel that is suitable for current resolution.

  GTK takes pixels as its unit in many function calls. To maintain the
  consistency of the UI in different resolution, a conversion is required.
  Take current resolution and (_UI_SCREEN_WIDTH, _UI_SCREEN_HEIGHT) as
  the original resolution, this function returns a pair of width and height
  that is converted for current resolution.

  Because pixels in negative usually indicates unspecified, no conversion
  will be done for negative pixels.

  In addition, the aspect ratio is not maintained in this function.

  Usage Example:
    width,_ = convert_pixels((20,-1))

  @param size: A pair of pixels that designed under original resolution.
  @return: A pair of pixels of (width, height) format.
       Pixels returned are always integer.
  """
  return (int(float(size[0]) / _UI_SCREEN_WIDTH * gtk.gdk.screen_width()
      if (size[0] > 0) else size[0]),
      int(float(size[1]) / _UI_SCREEN_HEIGHT * gtk.gdk.screen_height()
      if (size[1] > 0) else size[1]))


def make_hsep(height=1):
  """Returns a widget acts as a horizontal separation line.

  The unit is pixels under resolution _UI_SCREEN_WIDTH*_UI_SCREEN_HEIGHT.
  """
  frame = gtk.EventBox()
  # Convert height according to the current resolution.
  frame.set_size_request(*convert_pixels((-1, height)))
  frame.modify_bg(gtk.STATE_NORMAL, SEP_COLOR)
  return frame


def make_vsep(width=1):
  """Returns a widget acts as a vertical separation line.

  The unit is pixels under resolution _UI_SCREEN_WIDTH*_UI_SCREEN_HEIGHT.
  """
  frame = gtk.EventBox()
  # Convert width according to the current resolution.
  frame.set_size_request(*convert_pixels((width, -1)))
  frame.modify_bg(gtk.STATE_NORMAL, SEP_COLOR)
  return frame


def make_countdown_widget(prompt=None, value=None, fg=LIGHT_GREEN):
  if prompt is None:
    prompt = 'time remaining / 剩余时间: '
  if value is None:
    value = '%s' % FAIL_TIMEOUT
  title = make_label(prompt, fg=fg, alignment=(1, 0.5))
  countdown = make_label(value, fg=fg, alignment=(0, 0.5))
  hbox = gtk.HBox()
  hbox.pack_start(title)
  hbox.pack_start(countdown)
  eb = gtk.EventBox()
  eb.modify_bg(gtk.STATE_NORMAL, BLACK)
  eb.add(hbox)
  return eb, countdown


def is_chrome_ui():
  return os.environ.get('CROS_UI') == 'chrome'


def hide_cursor(gdk_window):
  pixmap = gtk.gdk.Pixmap(None, 1, 1, 1)
  color = gtk.gdk.Color()
  cursor = gtk.gdk.Cursor(pixmap, pixmap, color, color, 0, 0)
  gdk_window.set_cursor(cursor)


def calc_scale(wanted_x, wanted_y):
  (widget_size_x, widget_size_y) = factory.get_shared_data('test_widget_size')
  scale_x = (0.9 * widget_size_x) / wanted_x
  scale_y = (0.9 * widget_size_y) / wanted_y
  scale = scale_y if scale_y < scale_x else scale_x
  scale = 1 if scale > 1 else scale
  factory.log('scale: %s' % scale)
  return scale


def trim(text, length):
  if len(text) > length:
    text = text[:length-3] + '...'
  return text


class InputError(ValueError):
  """Execption for input window callbacks to change status text message."""
  pass


def make_input_window(prompt=None,
           init_value=None,
           msg_invalid=None,
           font=None,
           on_validate=None,
           on_keypress=None,
           on_complete=None):
  """Creates a widget to prompt user for a valid string.

  @param prompt: A string to be displayed. None for default message.
  @param init_value: Initial value to be set.
  @param msg_invalid: Status string to display when input is invalid. None for
    default message.
  @param font: Font specification (string or pango.FontDescription) for label
    and entry. None for default large font.
  @param on_validate: A callback function to validate if the input from user
    is valid. None for allowing any non-empty input. Any ValueError or
    ui.InputError raised during execution in on_validate will be displayed
    in bottom status.
  @param on_keypress: A callback function when each keystroke is hit.
  @param on_complete: A callback function when a valid string is passed.
    None to stop (gtk.main_quit).
  @return: A widget with prompt, input entry, and status label. To access
    these elements, use attribute 'prompt', 'entry', and 'label'.
  """
  DEFAULT_MSG_INVALID = "Invalid input / 输入不正确"
  DEFAULT_PROMPT = "Enter Data / 输入资料:"

  def enter_callback(entry):
    text = entry.get_text()
    try:
      if (on_validate and (not on_validate(text))) or (not text.strip()):
        raise ValueError(msg_invalid)
      on_complete(text) if on_complete else gtk.main_quit()
    except ValueError as e:
      gtk.gdk.beep()
      status_label.set_text('ERROR: %s' % e.message)
    return True

  def key_press_callback(entry, key):
    status_label.set_text('')
    if on_keypress:
      return on_keypress(entry, key)
    return False

  # Populate default parameters
  if msg_invalid is None:
    msg_invalid = DEFAULT_MSG_INVALID

  if prompt is None:
    prompt = DEFAULT_PROMPT

  if font is None:
    font = LABEL_LARGE_FONT
  elif not isinstance(font, pango.FontDescription):
    font = pango.FontDescription(font)

  widget = gtk.VBox()
  label = make_label(prompt, font=font)
  status_label = make_label('', font=font)
  entry = gtk.Entry()
  entry.modify_font(font)
  entry.connect("activate", enter_callback)
  entry.connect("key_press_event", key_press_callback)
  if init_value:
    entry.set_text(init_value)
  widget.modify_bg(gtk.STATE_NORMAL, BLACK)
  status_label.modify_fg(gtk.STATE_NORMAL, RED)
  widget.add(label)
  widget.pack_start(entry)
  widget.pack_start(status_label)

  widget.entry = entry
  widget.status = status_label
  widget.prompt = label

  # TODO(itspeter) Replace deprecated get_entry by widget.entry.
  # Method for getting the entry.
  widget.get_entry = lambda : entry
  return widget


def make_summary_box(tests, state_map, rows=15):
  '''Creates a widget display status of a set of test.

  @param tests: A list of FactoryTest nodes whose status (and children's
    status) should be displayed.
  @param state_map: The state map as provide by the state instance.
  @param rows: The number of rows to display.
  @return: A tuple (widget, label_map), where widget is the widget, and
    label_map is a map from each test to the corresponding label.
  '''
  LABEL_EN_SIZE = (170, 35)
  LABEL_EN_SIZE_2 = (450, 25)
  LABEL_EN_FONT = pango.FontDescription('courier new extra-condensed 16')

  all_tests = sum([list(t.walk(in_order=True)) for t in tests], [])
  columns = len(all_tests) / rows + (len(all_tests) % rows != 0)

  info_box = gtk.HBox()
  info_box.set_spacing(20)
  for status in (TestState.ACTIVE, TestState.PASSED,
          TestState.FAILED, TestState.UNTESTED):
    label = make_label(status,
                size=LABEL_EN_SIZE,
                font=LABEL_EN_FONT,
                alignment=(0.5, 0.5),
                fg=LABEL_COLORS[status])
    info_box.pack_start(label, False, False)

  vbox = gtk.VBox()
  vbox.set_spacing(20)
  vbox.pack_start(info_box, False, False)

  label_map = {}

  if all_tests:
    status_table = gtk.Table(rows, columns, True)
    for (j, i), t in izip(product(xrange(columns), xrange(rows)),
               all_tests):
      msg_en = ' ' * (t.depth() - 1) + t.label_en
      msg_en = trim(msg_en, 12)
      if t.label_zh:
        msg = '{0:<12} ({1})'.format(msg_en, t.label_zh)
      else:
        msg = msg_en
      status = state_map[t].status
      status_label = make_label(msg,
                   size=LABEL_EN_SIZE_2,
                   font=LABEL_EN_FONT,
                   alignment=(0.0, 0.5),
                   fg=LABEL_COLORS[status])
      label_map[t] = status_label
      status_table.attach(status_label, j, j+1, i, i+1)
    vbox.pack_start(status_table, False, False)

  return vbox, label_map


def run_test_widget(dummy_job, test_widget,
          invisible_cursor=True,
          window_registration_callback=None,
          cleanup_callback=None):
  test_widget_size = factory.get_shared_data('test_widget_size')

  window = gtk.Window(gtk.WINDOW_TOPLEVEL)
  window.modify_bg(gtk.STATE_NORMAL, BLACK)
  window.set_size_request(*test_widget_size)

  test_widget_position = factory.get_shared_data('test_widget_position')
  if test_widget_position:
    window.move(*test_widget_position)

  def show_window():
    window.show()
    window.window.raise_() # pylint: disable=E1101
    if is_chrome_ui():
      window.present()
      window.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.LEFT_PTR))
    else:
      gtk.gdk.pointer_grab(window.window, confine_to=window.window)
      if invisible_cursor:
        hide_cursor(window.window)

  test_path = factory.get_current_test_path()

  def handle_event(event):
    if (event.type == Event.Type.STATE_CHANGE and
      test_path and event.path == test_path):
      if event.state.visible:
        show_window()
      else:
        window.hide()

  event_client = EventClient(
      callback=handle_event, event_loop=EventClient.EVENT_LOOP_GOBJECT_IO)

  align = gtk.Alignment(xalign=0.5, yalign=0.5)
  align.add(test_widget)

  window.add(align)
  for c in window.get_children():
    # Show all children, but not the window itself yet.
    c.show_all()

  if window_registration_callback is not None:
    window_registration_callback(window)

  # Show the window if it is the visible test, or if the test_path is not
  # available (e.g., run directly from the command line).
  if (not test_path) or (
    TestState.from_dict_or_object(
      factory.get_state_instance().get_test_state(test_path)).visible):
    show_window()
  else:
    window.hide()

  # When gtk.main() is running, it ignores all uncaught exceptions, which is
  # not preferred by most of our factory tests. To prevent writing special
  # function raising errors, we hook top level exception handler to always
  # leave GTK main and raise exception again.

  def exception_hook(exc_type, value, traceback):
    # Prevent re-entrant.
    sys.excepthook = old_excepthook
    session['exception'] = (exc_type, value, traceback)
    gobject.idle_add(gtk.main_quit)
    return old_excepthook(exc_type, value, traceback)

  session = {}
  old_excepthook = sys.excepthook
  sys.excepthook = exception_hook

  gtk.main()

  if not is_chrome_ui():
    gtk.gdk.pointer_ungrab()

  if cleanup_callback is not None:
    cleanup_callback()

  del event_client

  sys.excepthook = old_excepthook
  exc_info = session.get('exception')
  if exc_info is not None:
    logging.error(exc_info[0], exc_info=exc_info)
    raise FactoryTestFailure(exc_info[1])



# ---------------------------------------------------------------------------
# Server Implementation


class Console(object):
  '''Display a progress log. Implemented by launching an borderless
  xterm at a strategic location, and running tail against the log.'''

  def __init__(self, allocation):
    # Specify how many lines and characters per line are displayed.
    XTERM_DISPLAY_LINES = 13
    XTERM_DISPLAY_CHARS = 120
    # Extra space reserved for pixels between lines.
    XTERM_RESERVED_LINES = 3

    xterm_coords = '%dx%d+%d+%d' % (XTERM_DISPLAY_CHARS,
                    XTERM_DISPLAY_LINES,
                    allocation.x,
                    allocation.y)
    xterm_reserved_height = gtk.gdk.screen_height() - allocation.y
    font_size = int(float(xterm_reserved_height) / (XTERM_DISPLAY_LINES +
                            XTERM_RESERVED_LINES))
    logging.info('xterm_reserved_height = %d' % xterm_reserved_height)
    logging.info('font_size = %d' % font_size)
    logging.info('xterm_coords = %s', xterm_coords)
    xterm_opts = ('-bg black -fg lightgray -bw 0 -g %s' % xterm_coords)
    xterm_cmd = (
      ['urxvt'] + xterm_opts.split() +
      ['-fn', 'xft:DejaVu Sans Mono:pixelsize=%s' % font_size] +
      ['-e', 'bash'] +
      ['-c', 'tail -f "%s"' % factory.CONSOLE_LOG_PATH])
    logging.info('xterm_cmd = %s', xterm_cmd)
    self._proc = subprocess.Popen(xterm_cmd)

  def __del__(self):
    logging.info('console_proc __del__')
    self._proc.kill()


class TestLabelBox(gtk.EventBox): # pylint: disable=R0904

  def __init__(self, test):
    gtk.EventBox.__init__(self)
    self.modify_bg(gtk.STATE_NORMAL, LABEL_COLORS[TestState.UNTESTED])
    self._is_group = test.is_group()
    depth = len(test.get_ancestor_groups())
    self._label_text = ' %s%s%s' % (
        ' ' * depth,
        SYMBOL_RIGHT_ARROW if self._is_group else ' ',
        test.label_en)
    if self._is_group:
      self._label_text_collapsed = ' %s%s%s' % (
          ' ' * depth,
          SYMBOL_DOWN_ARROW if self._is_group else '',
          test.label_en)
    self._label_en = make_label(
      self._label_text, size=_LABEL_EN_SIZE,
      font=_LABEL_EN_FONT, alignment=(0, 0.5),
      fg=_LABEL_UNTESTED_FG)
    self._label_zh = make_label(
      test.label_zh, size=_LABEL_ZH_SIZE,
      font=_LABEL_ZH_FONT, alignment=(0.5, 0.5),
      fg=_LABEL_UNTESTED_FG)
    self._label_t = make_label(
      '', size=_LABEL_T_SIZE, font=_LABEL_T_FONT,
      alignment=(0.5, 0.5), fg=BLACK)
    hbox = gtk.HBox()
    hbox.pack_start(self._label_en, False, False)
    hbox.pack_start(self._label_zh, False, False)
    hbox.pack_start(self._label_t, False, False)
    vbox = gtk.VBox()
    vbox.pack_start(hbox, False, False)
    vbox.pack_start(make_hsep(), False, False)
    self.add(vbox)
    self._status = None

  def set_shortcut(self, shortcut):
    if shortcut is None:
      return
    self._label_t.set_text('C-%s' % shortcut.upper())
    attrs = self._label_en.get_attributes() or pango.AttrList()
    attrs.filter(lambda attr: attr.type == pango.ATTR_UNDERLINE)
    index_hotkey = self._label_en.get_text().upper().find(shortcut.upper())
    if index_hotkey != -1:
      attrs.insert(pango.AttrUnderline(
        pango.UNDERLINE_LOW, index_hotkey, index_hotkey + 1))
      attrs.insert(pango.AttrWeight(
        pango.WEIGHT_BOLD, index_hotkey, index_hotkey + 1))
    self._label_en.set_attributes(attrs)
    self.queue_draw()

  def update(self, status):
    if self._status == status:
      return
    self._status = status
    label_fg = (_LABEL_UNTESTED_FG if status == TestState.UNTESTED
          else BLACK)
    if self._is_group:
      self._label_en.set_text(
          self._label_text_collapsed if status == TestState.ACTIVE
          else self._label_text)

    for label in [self._label_en, self._label_zh, self._label_t]:
      label.modify_fg(gtk.STATE_NORMAL, label_fg)
    self.modify_bg(gtk.STATE_NORMAL, LABEL_COLORS[status])
    self.queue_draw()


class ReviewInformation(object):

  LABEL_EN_FONT = pango.FontDescription('courier new extra-condensed 16')
  TAB_BORDER = 20

  def __init__(self, test_list):
    self.test_list = test_list

  def make_error_tab(self, test, state):
    msg = '%s (%s)\n%s' % (test.label_en, test.label_zh,
                str(state.error_msg))
    label = make_label(msg, font=self.LABEL_EN_FONT, alignment=(0.0, 0.0))
    label.set_line_wrap(True)
    frame = gtk.Frame()
    frame.add(label)
    return frame

  def make_widget(self):
    bg_color = gtk.gdk.Color(0x1000, 0x1000, 0x1000)
    self.notebook = gtk.Notebook()
    self.notebook.modify_bg(gtk.STATE_NORMAL, bg_color)

    test_list = self.test_list
    state_map = test_list.get_state_map()
    tab, _ = make_summary_box([test_list], state_map)
    tab.set_border_width(self.TAB_BORDER)
    self.notebook.append_page(tab, make_label('Summary'))

    for i, t in izip(
      count(1),
      [t for t in test_list.walk()
       if state_map[t].status == factory.TestState.FAILED
       and t.is_leaf()]):
      tab = self.make_error_tab(t, state_map[t])
      tab.set_border_width(self.TAB_BORDER)
      self.notebook.append_page(tab, make_label('#%02d' % i))

    prompt = 'Review: Test Status Information'
    if self.notebook.get_n_pages() > 1:
      prompt += '\nPress left/right to change tabs'

    control_label = make_label(prompt, font=self.LABEL_EN_FONT,
                  alignment=(0.5, 0.5))
    vbox = gtk.VBox()
    vbox.set_spacing(self.TAB_BORDER)
    vbox.pack_start(control_label, False, False)
    vbox.pack_start(self.notebook, False, False)
    vbox.show_all()
    vbox.grab_focus = self.notebook.grab_focus
    return vbox


class TestDirectory(gtk.VBox):
  '''Widget containing a list of tests, colored by test status.

  This is the widget corresponding to the RHS test panel.

  Attributes:
   _label_map: Dict of test path to TestLabelBox objects. Should
     contain an entry for each test that has been visible at some
     time.
   _visible_status: List of (test, status) pairs reflecting the
     last refresh of the set of visible tests. This is used to
     rememeber what tests were active, to allow implementation of
     visual refresh only when new active tests appear.
   _shortcut_map: Dict of keyboard shortcut key to test path.
     Tracks the current set of keyboard shortcut mappings for the
     visible set of tests. This will change when the visible
     test set changes.
  '''

  def __init__(self, test_list):
    gtk.VBox.__init__(self)
    self.set_spacing(0)
    self._label_map = {}
    self._visible_status = []
    self._shortcut_map = {}
    self._hard_shortcuts = set(
      test.kbd_shortcut for test in test_list.walk()
      if test.kbd_shortcut is not None)

  def _get_test_label(self, test):
    if test.path in self._label_map:
      return self._label_map[test.path]
    label_box = TestLabelBox(test)
    self._label_map[test.path] = label_box
    return label_box

  def _remove_shortcut(self, path):
    reverse_map = dict((v, k) for k, v in self._shortcut_map.items())
    if path not in reverse_map:
      logging.error('Removal of non-present shortcut for %s' % path)
      return
    shortcut = reverse_map[path]
    del self._shortcut_map[shortcut]

  def _add_shortcut(self, test):
    shortcut = test.kbd_shortcut
    if shortcut in self._shortcut_map:
      logging.error('Shortcut %s already in use by %s; cannot apply to %s'
             % (shortcut, self._shortcut_map[shortcut], test.path))
      shortcut = None
    if shortcut is None:
      # Find a suitable shortcut. For groups, use numbers. For
      # regular tests, use alpha (letters).
      if test.is_group():
        gen = (x for x in string.digits if x not in self._shortcut_map)
      else:
        gen = (x for x in test.label_en.lower() + string.lowercase
            if x.isalnum() and x not in self._shortcut_map
            and x not in self._hard_shortcuts)
      shortcut = next(gen, None)
    if shortcut is None:
      logging.error('Unable to find shortcut for %s' % test.path)
      return
    self._shortcut_map[shortcut] = test.path
    return shortcut

  def handle_xevent(self, dummy_src, dummy_cond,
           xhandle, keycode_map, event_client):
    for dummy_i in range(0, xhandle.pending_events()):
      xevent = xhandle.next_event()
      if xevent.type != X.KeyPress:
        continue
      keycode = xevent.detail
      if keycode not in keycode_map:
        logging.warning('Ignoring unknown keycode %r' % keycode)
        continue
      shortcut = keycode_map[keycode]

      if (xevent.state & GLOBAL_HOT_KEY_MASK == GLOBAL_HOT_KEY_MASK):
        event_type = GLOBAL_HOT_KEY_EVENTS.get(shortcut)
        if event_type:
          event_client.post_event(Event(event_type))
        else:
          logging.warning('Unbound global hot key %s', key)
      else:
        if shortcut not in self._shortcut_map:
          logging.warning('Ignoring unbound shortcut %r' % shortcut)
          continue
        test_path = self._shortcut_map[shortcut]
        event_client.post_event(Event(Event.Type.SWITCH_TEST,
                       path=test_path))
    return True

  def update(self, new_test_status):
    '''Refresh the RHS test list to show current status and active groups.

    Refresh the set of visible tests only when new active tests
    arise. This avoids visual volatility when switching between
    tests (intervals where no test is active). Also refresh at
    initial startup.

    Args:
     new_test_status: A list of (test, status) tuples. The tests
       order should match how they should be displayed in the
       directory (rhs panel).
    '''
    old_active = set(t for t, s in self._visible_status
             if s == TestState.ACTIVE)
    new_active = set(t for t, s in new_test_status
             if s == TestState.ACTIVE)
    new_visible = set(t for t, s in new_test_status)
    old_visible = set(t for t, s in self._visible_status)

    if old_active and not new_active - old_active:
      # No new active tests, so do not change the displayed test
      # set, only update the displayed status for currently
      # visible tests. Not updating _visible_status allows us
      # to remember the last set of active tests.
      for test, _ in self._visible_status:
        status = test.get_state().status
        self._label_map[test.path].update(status)
      return

    self._visible_status = new_test_status

    new_test_map = dict((t.path, t) for t, s in new_test_status)

    for test in old_visible - new_visible:
      label_box = self._label_map[test.path]
      logging.debug('removing %s test label' % test.path)
      self.remove(label_box)
      self._remove_shortcut(test.path)

    new_tests = new_visible - old_visible

    for position, (test, status) in enumerate(new_test_status):
      label_box = self._get_test_label(test)
      if test in new_tests:
        shortcut = self._add_shortcut(test)
        label_box = self._get_test_label(test)
        label_box.set_shortcut(shortcut)
        logging.debug('adding %s test label (sortcut %r, pos %d)' %
               (test.path, shortcut, position))
        self.pack_start(label_box, False, False)
      self.reorder_child(label_box, position)
      label_box.update(status)

    self.show_all()



class UiState(object):

  WIDGET_NONE = 0
  WIDGET_IDLE = 1
  WIDGET_SUMMARY = 2
  WIDGET_REVIEW = 3

  def __init__(self, test_widget_box, test_directory_widget, test_list):
    self._test_widget_box = test_widget_box
    self._test_directory_widget = test_directory_widget
    self._test_list = test_list
    self._transition_count = 0
    self._active_test_label_map = None
    self._active_widget = self.WIDGET_NONE
    self.update_test_state()

  def show_idle_widget(self):
    self.remove_state_widget()
    self._test_widget_box.set(0.5, 0.5, 0.0, 0.0)
    self._test_widget_box.set_padding(0, 0, 0, 0)
    label = make_label(MESSAGE_NO_ACTIVE_TESTS,
              font=_OTHER_LABEL_FONT,
              alignment=(0.5, 0.5))
    self._test_widget_box.add(label)
    self._test_widget_box.show_all()
    self._active_widget = self.WIDGET_IDLE

  def show_summary_widget(self):
    self.remove_state_widget()
    state_map = self._test_list.get_state_map()
    self._test_widget_box.set(0.5, 0.0, 0.0, 0.0)
    self._test_widget_box.set_padding(40, 0, 0, 0)
    vbox, self._active_test_label_map = make_summary_box(
      [t for t in self._test_list.subtests
       if state_map[t].status == TestState.ACTIVE],
      state_map)
    self._test_widget_box.add(vbox)
    self._test_widget_box.show_all()
    self._active_widget = self.WIDGET_SUMMARY

  def show_review_widget(self):
    self.remove_state_widget()
    self._review_request = False
    self._test_widget_box.set(0.5, 0.5, 0.0, 0.0)
    self._test_widget_box.set_padding(0, 0, 0, 0)
    widget = ReviewInformation(self._test_list).make_widget()
    self._test_widget_box.add(widget)
    self._test_widget_box.show_all()
    widget.grab_focus()
    self._active_widget = self.WIDGET_REVIEW

  def remove_state_widget(self):
    for child in self._test_widget_box.get_children():
      child.hide()
      self._test_widget_box.remove(child)
    self._active_test_label_map = None
    self._active_widget = self.WIDGET_NONE

  def update_test_state(self):
    state_map = self._test_list.get_state_map()
    active_tests = set(
      t for t in self._test_list.walk()
      if t.is_leaf() and state_map[t].status == TestState.ACTIVE)
    active_groups = set(g for t in active_tests
              for g in t.get_ancestor_groups())

    def filter_visible_test_state(tests):
      '''List currently visible tests and their status.

      Visible means currently displayed in the RHS panel.
      Visiblity is implied by being a top level test or having
      membership in a group with at least one active test.

      Returns:
       A list of (test, status) tuples for all visible tests,
       in the order they should be displayed.
      '''
      results = []
      for test in tests:
        if test.is_group():
          results.append((test, TestState.UNTESTED))
          if test not in active_groups:
            continue
          results += filter_visible_test_state(test.subtests)
        else:
          results.append((test, state_map[test].status))
      return results

    visible_test_state = filter_visible_test_state(self._test_list.subtests)
    self._test_directory_widget.update(visible_test_state)

    if not active_tests:
      # Display the idle or review information screen.
      def waiting_for_transition():
        return (self._active_widget not in
            [self.WIDGET_REVIEW, self.WIDGET_IDLE])

      # For smooth transition between tests, idle widget if activated only
      # after _NO_ACTIVE_TEST_DELAY_MS without state change.
      def idle_transition_check(cookie):
        if (waiting_for_transition() and
          cookie == self._transition_count):
          self._transition_count += 1
          self.show_idle_widget()
        return False

      if waiting_for_transition():
        gobject.timeout_add(_NO_ACTIVE_TEST_DELAY_MS,
                  idle_transition_check,
                  self._transition_count)
      return

    self._transition_count += 1

    if any(t.has_ui for t in active_tests):
      # Remove the widget (if any) since there is an active test
      # with a UI.
      self.remove_state_widget()
      return

    if (self._active_test_label_map is not None and
      all(t in self._active_test_label_map for t in active_tests)):
      # All active tests are already present in the summary, so just
      # update their states.
      for test, label in self._active_test_label_map.iteritems():
        label.modify_fg(
          gtk.STATE_NORMAL,
          LABEL_COLORS[state_map[test].status])
      return

    # No active UI; draw summary of current test states
    self.show_summary_widget()


def grab_shortcut_keys(disp, event_handler, event_client):
  # We want to receive KeyPress events
  root = disp.screen().root
  root.change_attributes(event_mask = X.KeyPressMask)
  shortcut_set = set(string.lowercase + string.digits)
  keycode_map = {}
  for mod, shortcut in ([(X.ControlMask, k) for k in shortcut_set] +
             [(GLOBAL_HOT_KEY_MASK, k)
              for k in GLOBAL_HOT_KEY_EVENTS] +
             [(X.Mod1Mask, 'Tab')]): # Mod1 = Alt
    keysym = gtk.gdk.keyval_from_name(shortcut)
    keycode = disp.keysym_to_keycode(keysym)
    keycode_map[keycode] = shortcut
    root.grab_key(keycode, mod, 1, X.GrabModeAsync, X.GrabModeAsync)
  # This flushes the XGrabKey calls to the server.
  for dummy_x in range(0, root.display.pending_events()):
    root.display.next_event()
  gobject.io_add_watch(root.display, gobject.IO_IN, event_handler,
             root.display, keycode_map, event_client)


def start_reposition_thread(title_regexp):
  '''Starts a thread to reposition a client window once it appears.

  This is useful to avoid blocking the console.

  Args:
   title_regexp: A regexp for the window's title (used to find the
    window to reposition).
  '''
  test_widget_position = (
    factory.get_shared_data('test_widget_position'))
  if not test_widget_position:
    return

  def reposition():
    display = Display()
    root = display.screen().root
    for i in xrange(50):
      wins = [win for win in root.query_tree().children
          if re.match(title_regexp, win.get_wm_name())]
      if wins:
        wins[0].configure(x=test_widget_position[0],
                 y=test_widget_position[1])
        display.sync()
        return
      # Wait 100 ms and try again.
      time.sleep(.1)
  thread = threading.Thread(target=reposition)
  thread.daemon = True
  thread.start()


def main(test_list_path):
  '''Starts the main UI.

  This is launched by the autotest/cros/factory/client.
  When operators press keyboard shortcuts, the shortcut
  value is sent as an event to the control program.'''

  test_list = None
  ui_state = None
  event_client = None

  def handle_key_release_event(_, event):
    logging.info('base ui key event (%s)', event.keyval)
    return True

  def handle_event(event):
    if event.type == Event.Type.STATE_CHANGE:
      ui_state.update_test_state()
    elif event.type == Event.Type.REVIEW:
      logging.info("Operator activates review information screen")
      ui_state.show_review_widget()

  test_list = factory.read_test_list(test_list_path)

  window = gtk.Window(gtk.WINDOW_TOPLEVEL)
  window.connect('destroy', lambda _: gtk.main_quit())
  window.modify_bg(gtk.STATE_NORMAL, BLACK)

  disp = Display()

  event_client = EventClient(
    callback=handle_event,
    event_loop=EventClient.EVENT_LOOP_GOBJECT_IO)

  screen = window.get_screen()
  if (screen is None):
    logging.info('ERROR: communication with the X server is not working, ' +
          'could not find a working screen. UI exiting.')
    sys.exit(1)

  screen_size_str = os.environ.get('CROS_SCREEN_SIZE')
  if screen_size_str:
    match = re.match(r'^(\d+)x(\d+)$', screen_size_str)
    assert match, 'CROS_SCREEN_SIZE should be {width}x{height}'
    screen_size = (int(match.group(1)), int(match.group(2)))
  else:
    screen_size = (screen.get_width(), screen.get_height())
  window.set_size_request(*screen_size)

  test_directory = TestDirectory(test_list)

  rhs_box = gtk.EventBox()
  rhs_box.modify_bg(gtk.STATE_NORMAL, _LABEL_TROUGH_COLOR)
  rhs_box.add(test_directory)

  console_box = gtk.EventBox()
  console_box.set_size_request(*convert_pixels((-1, 180)))
  console_box.modify_bg(gtk.STATE_NORMAL, BLACK)

  test_widget_box = gtk.Alignment()
  test_widget_box.set_size_request(-1, -1)

  lhs_box = gtk.VBox()
  lhs_box.pack_end(console_box, False, False)
  lhs_box.pack_start(test_widget_box)
  lhs_box.pack_start(make_hsep(3), False, False)

  base_box = gtk.HBox()
  base_box.pack_end(rhs_box, False, False)
  base_box.pack_end(make_vsep(3), False, False)
  base_box.pack_start(lhs_box)

  window.connect('key-release-event', handle_key_release_event)
  window.add_events(gtk.gdk.KEY_RELEASE_MASK)

  ui_state = UiState(test_widget_box, test_directory, test_list)

  window.add(base_box)
  window.show_all()

  grab_shortcut_keys(disp, test_directory.handle_xevent, event_client)

  hide_cursor(window.window)

  test_widget_allocation = test_widget_box.get_allocation()
  test_widget_size = (test_widget_allocation.width,
            test_widget_allocation.height)
  factory.set_shared_data('test_widget_size', test_widget_size)

  if not factory.in_chroot():
    dummy_console = Console(console_box.get_allocation())

  event_client.post_event(Event(Event.Type.UI_READY))

  logging.info('cros/factory/ui setup done, starting gtk.main()...')
  gtk.main()
  logging.info('cros/factory/ui gtk.main() finished, exiting.')


if __name__ == '__main__':
  parser = OptionParser(usage='usage: %prog [options] TEST-LIST-PATH')
  parser.add_option('-v', '--verbose', dest='verbose',
           action='store_true',
           help='Enable debug logging')
  (options, args) = parser.parse_args()

  if len(args) != 1:
    parser.error('Incorrect number of arguments')

  factory.init_logging('ui', verbose=options.verbose)
  main(sys.argv[1])
