#!/usr/bin/python -u
# -*- coding: utf-8 -*-
#
# Copyright (c) 2010 The Chromium OS Authors. All rights reserved.
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
# 'test list' panel on the right hand side of the screen.  The
# majority of the screen is dedicated to tests, which are executed in
# seperate processes, but instructed to display their own UIs in this
# dedicated area whenever possible.  Tests in the test list are
# executed in order by default, but can be activated on demand via
# associated keyboard shortcuts.  As tests are run, their status is
# color-indicated to the operator -- greyed out means untested, yellow
# means active, green passed and red failed.

import logging
import os
import re
import subprocess
import sys
from itertools import izip, product

# GTK and X modules
import gobject
import gtk
import pango

# Factory and autotest modules
import factory_common
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import TestState
from autotest_lib.client.cros.factory.event import Event, EventClient


# For compatibility with tests before TestState existed
ACTIVE = TestState.ACTIVE
PASSED = TestState.PASSED
FAILED = TestState.FAILED
UNTESTED = TestState.UNTESTED

# Color definition
BLACK = gtk.gdk.Color()
RED =   gtk.gdk.Color(0xFFFF, 0, 0)
GREEN = gtk.gdk.Color(0, 0xFFFF, 0)
BLUE =  gtk.gdk.Color(0, 0, 0xFFFF)
WHITE = gtk.gdk.Color(0xFFFF, 0xFFFF, 0xFFFF)
LIGHT_GREEN = gtk.gdk.color_parse('light green')
SEP_COLOR = gtk.gdk.color_parse('grey50')

RGBA_GREEN_OVERLAY = (0, 0.5, 0, 0.6)
RGBA_YELLOW_OVERLAY = (0.6, 0.6, 0, 0.6)

LABEL_COLORS = {
    TestState.ACTIVE: gtk.gdk.color_parse('light goldenrod'),
    TestState.PASSED: gtk.gdk.color_parse('pale green'),
    TestState.FAILED: gtk.gdk.color_parse('tomato'),
    TestState.UNTESTED: gtk.gdk.color_parse('dark slate grey')}

LABEL_FONT = pango.FontDescription('courier new condensed 16')
LABEL_LARGE_FONT = pango.FontDescription('courier new condensed 24')

FAIL_TIMEOUT = 30

USER_PASS_FAIL_SELECT_STR = (
    'hit TAB to fail and ENTER to pass\n' +
    '錯誤請按 TAB，成功請按 ENTER')

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

_ST_LABEL_EN_SIZE = (250, 35)
_ST_LABEL_ZH_SIZE = (150, 35)

_NO_ACTIVE_TEST_DELAY_MS = 500


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
    l = gtk.Label(message)
    l.modify_font(font)
    l.modify_fg(gtk.STATE_NORMAL, fg)
    if size:
        l.set_size_request(*size)
    if alignment:
        l.set_alignment(*alignment)
    return l


def make_hsep(width=1):
    frame = gtk.EventBox()
    frame.set_size_request(-1, width)
    frame.modify_bg(gtk.STATE_NORMAL, SEP_COLOR)
    return frame


def make_vsep(width=1):
    frame = gtk.EventBox()
    frame.set_size_request(width, -1)
    frame.modify_bg(gtk.STATE_NORMAL, SEP_COLOR)
    return frame


def make_countdown_widget():
    title = make_label('time remaining / 剩餘時間: ', alignment=(1, 0.5))
    countdown = make_label('%d' % FAIL_TIMEOUT, alignment=(0, 0.5))
    hbox = gtk.HBox()
    hbox.pack_start(title)
    hbox.pack_start(countdown)
    eb = gtk.EventBox()
    eb.modify_bg(gtk.STATE_NORMAL, BLACK)
    eb.add(hbox)
    return eb, countdown


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


def make_input_window(prompt=None,
                      init_value=None,
                      msg_invalid=None,
                      font=None,
                      on_validate=None,
                      on_keypress=None,
                      on_complete=None):
    """
    Creates a widget to prompt user for a valid string.

    @param prompt: A string to be displayed. None for default message.
    @param init_value: Initial value to be set.
    @param msg_invalid: Status string to display when input is invalid. None for
        default message.
    @param font: Font specification (string or pango.FontDescription) for label
        and entry. None for default large font.
    @param on_validate: A callback function to validate if the input from user
        is valid. None for allowing any non-empty input.
    @param on_keypress: A callback function when each keystroke is hit.
    @param on_complete: A callback function when a valid string is passed.
        None to stop (gtk.main_quit).
    @return: A widget with prompt, input entry, and status label.
             In addition, a method called get_entry() is added to the widget to
             provide controls on the entry.
    """
    DEFAULT_MSG_INVALID = "Invalid input / 輸入不正確"
    DEFAULT_PROMPT = "Enter Data / 輸入資料:"

    def enter_callback(entry):
        text = entry.get_text()
        if (on_validate and (not on_validate(text))) or (not text.strip()):
            gtk.gdk.beep()
            status_label.set_text(msg_invalid)
        else:
            on_complete(text) if on_complete else gtk.main_quit()
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

    # Method for getting the entry.
    widget.get_entry = lambda : entry

    return widget


def make_summary_box(tests, state_map, rows=15):
    '''
    Creates a widget display status of a set of test.

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
            msg_en = '  ' * (t.depth() - 1) + t.label_en
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

    def show_window():
        window.show()
        window.window.raise_()  # pylint: disable=E1101
        gtk.gdk.pointer_grab(window.window, confine_to=window.window)
        if invisible_cursor:
            hide_cursor(window.window)

    test_path = factory.get_current_test_path()

    def handle_event(event):
        if (event.type == Event.Type.STATE_CHANGE and
            test_path and event.path == test_path and
            event.state.visible):
            show_window()

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

    gtk.main()

    gtk.gdk.pointer_ungrab()

    if cleanup_callback is not None:
        cleanup_callback()

    del event_client


# ---------------------------------------------------------------------------
# Server Implementation


class Console(object):
    '''Display a progress log.  Implemented by launching an borderless
    xterm at a strategic location, and running tail against the log.'''

    def __init__(self, allocation):
        xterm_coords = '145x13+%d+%d' % (allocation.x, allocation.y)
        logging.info('xterm_coords = %s', xterm_coords)
        xterm_opts = ('-bg black -fg lightgray -bw 0 -g %s' % xterm_coords)
        xterm_cmd = (('urxvt %s -e bash -c ' % xterm_opts).split() +
                     ['tail -f "%s"' % factory.CONSOLE_LOG_PATH])
        logging.info('xterm_cmd = %s', xterm_cmd)
        self._proc = subprocess.Popen(xterm_cmd)

    def __del__(self):
        logging.info('console_proc __del__')
        self._proc.kill()


class TestLabelBox(gtk.EventBox):  # pylint: disable=R0904

    def __init__(self, test, show_shortcut=False):
        gtk.EventBox.__init__(self)
        self.modify_bg(gtk.STATE_NORMAL, LABEL_COLORS[TestState.UNTESTED])

        label_en = make_label(test.label_en, size=_LABEL_EN_SIZE,
                              font=_LABEL_EN_FONT, alignment=(0.5, 0.5),
                              fg=_LABEL_UNTESTED_FG)
        label_zh = make_label(test.label_zh, size=_LABEL_ZH_SIZE,
                              font=_LABEL_ZH_FONT, alignment=(0.5, 0.5),
                              fg=_LABEL_UNTESTED_FG)
        label_t = make_label('C-' + test.kbd_shortcut.upper(),
                             size=_LABEL_T_SIZE, font=_LABEL_T_FONT,
                             alignment=(0.5, 0.5), fg=BLACK)

        # build a better label_en with shortcuts
        index_hotkey = test.label_en.upper().find(test.kbd_shortcut.upper())
        if show_shortcut and index_hotkey >= 0:
            attrs = label_en.get_attributes() or pango.AttrList()
            attrs.insert(pango.AttrUnderline(
                    pango.UNDERLINE_LOW, index_hotkey, index_hotkey + 1))
            attrs.insert(pango.AttrWeight(
                    pango.WEIGHT_BOLD, index_hotkey, index_hotkey + 1))
            label_en.set_attributes(attrs)

        hbox = gtk.HBox()
        hbox.pack_start(label_en, False, False)
        hbox.pack_start(label_zh, False, False)
        hbox.pack_start(label_t, False, False)
        self.add(hbox)
        self.label_list = [label_en, label_zh]

    def update(self, state):
        label_fg = (_LABEL_UNTESTED_FG if state.status == TestState.UNTESTED
                    else BLACK)
        for label in self.label_list:
            label.modify_fg(gtk.STATE_NORMAL, label_fg)
        self.modify_bg(gtk.STATE_NORMAL, LABEL_COLORS[state.status])
        self.queue_draw()


class UiState(object):

    def __init__(self, test_widget_box):
        self._test_widget_box = test_widget_box
        self._label_box_map = {}
        self._transition_count = 0

        self._active_test_label_map = None

    def _remove_state_widget(self):
        """Remove any existing state widgets."""
        for child in self._test_widget_box.get_children():
            self._test_widget_box.remove(child)
        self._active_test_label_map = None

    def update_test_label(self, test, state):
        label_box = self._label_box_map.get(test)
        if label_box:
            label_box.update(state)

    def update_test_state(self, test_list, state_map):
        active_tests = [
            t for t in test_list.walk()
            if t.is_leaf() and state_map[t].status == TestState.ACTIVE]
        has_active_ui = any(t.has_ui for t in active_tests)

        if not active_tests:
            # Display the "no active tests" widget if there are still no
            # active tests after _NO_ACTIVE_TEST_DELAY_MS.
            def run(transition_count):
                if transition_count != self._transition_count:
                    # Something has happened
                    return False

                self._transition_count += 1
                self._remove_state_widget()

                self._test_widget_box.set(0.5, 0.5, 0.0, 0.0)
                self._test_widget_box.set_padding(0, 0, 0, 0)
                label_box = gtk.EventBox()
                label_box.modify_bg(gtk.STATE_NORMAL, BLACK)
                label = make_label('no active test', font=_OTHER_LABEL_FONT,
                                   alignment=(0.5, 0.5))
                label_box.add(label)
                self._test_widget_box.add(label_box)
                self._test_widget_box.show_all()

            gobject.timeout_add(_NO_ACTIVE_TEST_DELAY_MS, run,
                                self._transition_count)
            return

        self._transition_count += 1

        if has_active_ui:
            # Remove the widget (if any) since there is an active test
            # with a UI.
            self._remove_state_widget()
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

        self._remove_state_widget()
        # No active UI; draw summary of current test states
        self._test_widget_box.set(0.5, 0.0, 0.0, 0.0)
        self._test_widget_box.set_padding(40, 0, 0, 0)
        vbox, self._active_test_label_map = make_summary_box(
            [t for t in test_list.subtests
             if state_map[t].status == TestState.ACTIVE],
            state_map)
        self._test_widget_box.add(vbox)
        self._test_widget_box.show_all()

    def set_label_box(self, test, label_box):
        self._label_box_map[test] = label_box


def main(test_list_path):
    '''Starts the main UI.

    This is launched by the autotest/cros/factory/client.
    When operators press keyboard shortcuts, the shortcut
    value is sent as an event to the control program.'''

    test_list = None
    ui_state = None
    event_client = None

    # Delay loading Xlib because Xlib is currently not available in image build
    # process host-depends list, and it's only required by the main UI, not all
    # the tests using UI library (in other words, it'll be slower and break the
    # build system if Xlib is globally imported).
    try:
        from Xlib import X
        from Xlib.display import Display
        disp = Display()
    except:
        logging.error('Failed loading X modules')
        raise

    def handle_key_release_event(_, event):
        logging.info('base ui key event (%s)', event.keyval)
        return True

    def handle_event(event):
        if event.type == Event.Type.STATE_CHANGE:
            test = test_list.lookup_path(event.path)
            state_map = test_list.get_state_map()
            ui_state.update_test_label(test, state_map[test])
            ui_state.update_test_state(test_list, state_map)

    def grab_shortcut_keys(kbd_shortcuts):
        root = disp.screen().root
        keycode_map = {}

        def handle_xevent(  # pylint: disable=W0102
                          dummy_src, dummy_cond, xhandle=root.display,
                          keycode_map=keycode_map):
            for dummy_i in range(0, xhandle.pending_events()):
                xevent = xhandle.next_event()
                if xevent.type == X.KeyPress:
                    keycode = xevent.detail
                    if keycode in keycode_map:
                        event_client.post_event(Event('kbd_shortcut',
                                                      key=keycode_map[keycode]))
                    else:
                        logging.warning('Unbound keycode %s' % keycode)
            return True

        # We want to receive KeyPress events
        root.change_attributes(event_mask = X.KeyPressMask)

        for mod, shortcut in ([(X.ControlMask, k) for k in kbd_shortcuts] +
                              [(X.Mod1Mask, 'Tab')]):  # Mod1 = Alt
            keysym = gtk.gdk.keyval_from_name(shortcut)
            keycode = disp.keysym_to_keycode(keysym)
            keycode_map[keycode] = shortcut
            root.grab_key(keycode, mod, 1,
                          X.GrabModeAsync, X.GrabModeAsync)

        # This flushes the XGrabKey calls to the server.
        for dummy_x in range(0, root.display.pending_events()):
            root.display.next_event()
        gobject.io_add_watch(root.display, gobject.IO_IN, handle_xevent)


    test_list = factory.read_test_list(test_list_path)

    window = gtk.Window(gtk.WINDOW_TOPLEVEL)
    window.connect('destroy', lambda _: gtk.main_quit())
    window.modify_bg(gtk.STATE_NORMAL, BLACK)

    event_client = EventClient(
        callback=handle_event,
        event_loop=EventClient.EVENT_LOOP_GOBJECT_IO)

    screen = window.get_screen()
    if (screen is None):
        logging.info('ERROR: communication with the X server is not working, ' +
                    'could not find a working screen.  UI exiting.')
        sys.exit(1)

    screen_size_str = os.environ.get('CROS_SCREEN_SIZE')
    if screen_size_str:
        match = re.match(r'^(\d+)x(\d+)$', screen_size_str)
        assert match, 'CROS_SCREEN_SIZE should be {width}x{height}'
        screen_size = (int(match.group(1)), int(match.group(2)))
    else:
        screen_size = (screen.get_width(), screen.get_height())
    window.set_size_request(*screen_size)

    label_trough = gtk.VBox()
    label_trough.set_spacing(0)

    rhs_box = gtk.EventBox()
    rhs_box.modify_bg(gtk.STATE_NORMAL, _LABEL_TROUGH_COLOR)
    rhs_box.add(label_trough)

    console_box = gtk.EventBox()
    console_box.set_size_request(-1, 180)
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

    ui_state = UiState(test_widget_box)

    for test in test_list.subtests:
        label_box = TestLabelBox(test, True)
        ui_state.set_label_box(test, label_box)
        label_trough.pack_start(label_box, False, False)
        label_trough.pack_start(make_hsep(), False, False)

    window.add(base_box)
    window.show_all()

    state_map = test_list.get_state_map()
    for test, state in test_list.get_state_map().iteritems():
        ui_state.update_test_label(test, state)
    ui_state.update_test_state(test_list, state_map)

    grab_shortcut_keys(test_list.kbd_shortcut_map.keys())

    hide_cursor(window.window)

    test_widget_allocation = test_widget_box.get_allocation()
    test_widget_size = (test_widget_allocation.width,
                        test_widget_allocation.height)
    factory.set_shared_data('test_widget_size', test_widget_size)

    dummy_console = Console(console_box.get_allocation())

    event_client.post_event(Event(Event.Type.UI_READY))

    logging.info('cros/factory/ui setup done, starting gtk.main()...')
    gtk.main()
    logging.info('cros/factory/ui gtk.main() finished, exiting.')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print 'usage: %s <test list path>' % sys.argv[0]
        sys.exit(1)

    factory.init_logging("cros/factory/ui", verbose=True)
    main(sys.argv[1])
