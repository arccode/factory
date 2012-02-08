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

import gobject, gtk, pango
from itertools import izip, product

import factory_common
from autotest_lib.client.cros import factory
from autotest_lib.client.cros.factory import TestState
from autotest_lib.client.cros.factory.event import Event, EventClient

# For compatibility with tests before TestState existed
ACTIVE = TestState.ACTIVE
PASSED = TestState.PASSED
FAILED = TestState.FAILED
UNTESTED = TestState.UNTESTED

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

FAIL_TIMEOUT = 30

USER_PASS_FAIL_SELECT_STR = (
    'hit TAB to fail and ENTER to pass\n' +
    '錯誤請按 TAB，成功請按 ENTER')


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
        callback=handle_event,
        event_loop=EventClient.EVENT_LOOP_GOBJECT_IO)

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
