# Copyright (c) 2013 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""This module provides MTB parser and related packet methods.

MTB stands for multi-touch type B protocol which allows kernel drivers
to report the touch data of finger contacts. For more information,
refers to "Multi-touch protocol":

  http://www.mjmwired.net/kernel/Documentation/input/multi-touch-protocol.txt

Here below describes the methods of parsing an evtest data file and access
the MTB attributes:

  # Parse the full-path filename to mtb_packets
  filename = '..../two_finger_tracking.bottom_left_to_top_right.slow.dat'
  mtb_packets = touch_utils.GetMtbPacketsFromFile(filename)

  # Get the points in the 0th finger contact (finger = 0) and print the points.
  points = mtb_packets.GetOrderedFingerPath(0, 'point')
  for point in points:
    print '(%d, %d)' % (point.x, point.y)

  # Get the SYN_REPORT time events in the 0th finger contact and print them.
  syn_times = mtb_packets.GetOrderedFingerPath(0, 'syn_time')
  for syn_time in syn_times:
    print 'SYN_REPORT time:', syn_time

  # Get the pressures in the 0th finger contact
  pressures = mtb_packets.GetOrderedFingerPath(0, 'pressure')
  for pressure in pressures:
    print 'Pressure:', pressure

  # How to get the number of finger contacts in the file?
  finger_paths = mtb_packets.GetOrderedFingerPaths()
  print 'The number of fingers: ', len(finger_paths)

  # How to get the TRACKING ID and the slot number of the 1st finger contact?
  # (Note: the finger contact starts from 0.)
  i = 0
  print 'Tracking ID of finger contact %d: %d' % (i, finger_paths.keys()[i])
  print 'Slot no of finger contact %d: %d' % (i, finger_paths.values()[i].slot)
"""

import copy
import logging
import math
import os
import re

from collections import namedtuple, OrderedDict

from evdev.ecodes import (ABS_MT_POSITION_X, ABS_MT_POSITION_Y,
                          ABS_MT_PRESSURE, ABS_MT_SLOT, ABS_MT_TRACKING_ID,
                          BTN_LEFT, BTN_TOOL_FINGER, BTN_TOOL_DOUBLETAP,
                          BTN_TOOL_TRIPLETAP, BTN_TOOL_QUADTAP,
                          BTN_TOOL_QUINTTAP, BTN_TOUCH, EV_ABS, EV_KEY)


# Define TidPacket to keep the point, pressure, and SYN_REPOT time of a packet.
# Tid stands for tracking ID which is a finger contact ID defined in MTB.
TidPacket = namedtuple('TidPacket', ['syn_time', 'point', 'pressure'])


class FingerPath(namedtuple('FingerPath', ['slot', 'tid_packets']), object):
  """Keeps the slot number and the list of tid packets of a finger.

  Defines FingerPath class to keep track of the slot, and a list of the
  packets of a finger (i.e., a tracking ID).
  """
  # Keep memory requirements low by preventing the creation of instance dict.
  __slots__ = ()

  def get(self, attr):
    """Gets the list of the specified attribute.

    Args:
      attr: the attribute to get from the tid packets
            An attribute could be 'point', 'pressure', or 'syn_time'.

    Returns:
      a list of requested attributes extracted from the tid packets
    """
    return [getattr(tid_packet, attr)
            for tid_packet in self.tid_packets]   # pylint: disable=E1101


# Define MTB to hold constants about MTB events.
MTB_NAMES = ['EV_TIME', 'EV_TYPE', 'EV_CODE', 'EV_VALUE', 'SYN_REPORT',
             'SLOT', 'POINTS']
MTB_VALUES = ['EV_TIME', 'EV_TYPE', 'EV_CODE', 'EV_VALUE', 'SYN_REPORT',
              'slot', 'points']
MTB = namedtuple('MTB', MTB_NAMES)(*MTB_VALUES)


# def get_mtb_packets_from_file(event_file):
def GetMtbPacketsFromFile(event_file):
  """A helper function to get MTB packets by parsing the event file.

  Args:
    event_file: an MTB event file

  Returns:
    an Mtb object
  """
  return Mtb(packets=MtbParser().ParseFile(event_file))


class Point:
  """A point class to hold MTB (x, y) coordinates.

  Note that the kernel driver only reports what is changed. Due to its
  internal state machine, it is possible that either x or y is None initially.
  """

  def __init__(self, x=None, y=None):
    """Initializes a point.

    Args:
      x: x coordinate
      y: y coordinate
    """
    self.x = x if x is None else float(x)
    self.y = y if y is None else float(y)

  def __bool__(self):
    """A boolean indicating if this point is defined.

    Returns:
      True if both x and y coordinates are not None
    """
    return self.x is not None and self.y is not None

  def __eq__(self, p):
    """Determines if this point is equal to the specified point, p.

    Args:
      p: a point

    Returns:
      True if the coordinate values are about equal within the TOLERANCE
    """
    return Point.AboutEq(self.x, p.x) and Point.AboutEq(self.y, p.y)

  def __hash__(self):
    """Redefines the hash function to meet the consistency requirement.

    In order to put an item into a set, it needs to be hashable.
    To make an object hashable, it must meet the consistency requirement:
        a == b must imply hash(a) == hash(b)

    Returns:
      the hash value of the point coordinates
    """
    return hash((self.x, self.y))

  def __str__(self):
    """The string representation of the point value.

    Returns:
      the string representation of the point value
    """
    convert = lambda c: '%.4f' % c if isinstance(c, float) else str(c)
    return 'Point: (%s, %s)' % tuple(map(convert, self.Value()))

  @staticmethod
  def AboutEq(f1, f2):
    """Determines if two numbers are about equal within the TOLERANCE.

    Args:
      f1: float number 1
      f2: float number 2

    Returns:
      True if the difference of values are within the TOLERANCE
    """
    TOLERANCE = 0.00000001
    return ((f1 is None and f2 is None) if (f1 is None or f2 is None) else
            abs(f1 - f2) < TOLERANCE)

  def Distance(self, p):
    """Calculates the distance between p and this point.

    Args:
      p: a point

    Returns:
      the distance between p and this point
    """
    return (math.sqrt((p.x - self.x) ** 2 + (p.y - self.y) ** 2 )
            if (self and p) else None)

  def Value(self):
    """Returns the point coordinates.

    Returns:
      the point coordinates (x, y)
    """
    return (self.x, self.y)

  # __bool__ is used in Python 3.x and __nonzero__ in Python 2.x
  __nonzero__ = __bool__


class MtbEvent(object):                           # pylint: disable=W0232
  """Determine what an MTB event is.

  This class is just a bundle of a variety of classmethods about
  MTB event classification.
  """
  @classmethod
  def IsAbsTypeWithCode(cls, event, ev_code):
    """Is this event with EV_ABS type and the specified event code?

    Args:
      event: an MTB event
      ev_code: the event code

    Returns:
      True if this event comes with the EV_ABS type and the specified event code
    """
    return (not event.get(MTB.SYN_REPORT) and
            event[MTB.EV_TYPE] == EV_ABS and event[MTB.EV_CODE] == ev_code)

  @classmethod
  def IsKeyTypeWithCode(cls, event, ev_code):
    """Is this event with EV_KEY type and the specified event code?

    Args:
      event: an MTB event
      ev_code: the event code

    Returns:
      True if this event comes with the EV_KEY type and the specified event code
    """
    return (not event.get(MTB.SYN_REPORT) and
            event[MTB.EV_TYPE] == EV_KEY and event[MTB.EV_CODE] == ev_code)

  @classmethod
  def IsAbsMtTrackingId(cls, event):
    """Is this event ABS_MT_TRACKING_ID?

    Args:
      event: an MTB event

    Returns:
      True if this is an ABS_MT_TRACKING_ID event
    """
    return cls.IsAbsTypeWithCode(event, ABS_MT_TRACKING_ID)

  @classmethod
  def IsNewContact(cls, event):
    """Is this packet generating new contact (Tracking ID)?

    Args:
      event: an MTB event

    Returns:
      True if the value of ABS_MT_TRACKING_ID is not -1
    """
    return cls.IsAbsMtTrackingId(event) and event[MTB.EV_VALUE] != -1

  @classmethod
  def IsFingerLeaving(cls, event):
    """Is the finger is leaving in this packet?

    Args:
      event: an MTB event

    Returns:
      True if the value of ABS_MT_TRACKING_ID is -1
    """
    return cls.IsAbsMtTrackingId(event) and event[MTB.EV_VALUE] == -1

  @classmethod
  def IsAbsMtSlot(cls, event):
    """Is this packet ABS_MT_SLOT?

    Args:
      event: an MTB event

    Returns:
      True if this is an ABS_MT_SLOT event
    """
    return cls.IsAbsTypeWithCode(event, ABS_MT_SLOT)

  @classmethod
  def IsAbsMtPositionX(cls, event):
    """Is this packet ABS_MT_POSITION_X?

    Args:
      event: an MTB event

    Returns:
      True if this is an ABS_MT_POSITION_X event
    """
    return cls.IsAbsTypeWithCode(event, ABS_MT_POSITION_X)

  @classmethod
  def IsAbsMtPositionY(cls, event):
    """Is this packet ABS_MT_POSITION_Y?

    Args:
      event: an MTB event

    Returns:
      True if this is an ABS_MT_POSITION_Y event
    """
    return cls.IsAbsTypeWithCode(event, ABS_MT_POSITION_Y)

  @classmethod
  def IsAbsMtPressure(cls, event):
    """Is this packet ABS_MT_PRESSURE?

    Args:
      event: an MTB event

    Returns:
      True if this is an ABS_MT_PRESSURE event
    """
    return cls.IsAbsTypeWithCode(event, ABS_MT_PRESSURE)

  @classmethod
  def IsBtnLeft(cls, event):
    """Is this event BTN_LEFT?

    Args:
      event: an MTB event

    Returns:
      True if this is a BTN_LEFT event
    """
    return cls.IsKeyTypeWithCode(event, BTN_LEFT)

  @classmethod
  def IsBtnLeftValue(cls, event, value):
    """Is this event BTN_LEFT with value equal to the specified value?

    Args:
      event: an MTB event
      value: the specified BTN_LEFT value

    Returns:
      True if the value of BTN_LEFT is equal to the sepcified value
    """
    return (cls.IsBtnLeft(event) and event[MTB.EV_VALUE] == value)

  @classmethod
  def IsBtnToolFinger(cls, event):
    """Is this event BTN_TOOL_FINGER?

    Args:
      event: an MTB event

    Returns:
      True if this is a BTN_TOOL_FINGER event
    """
    return cls.IsKeyTypeWithCode(event, BTN_TOOL_FINGER)

  @classmethod
  def IsBtnToolDoubletap(cls, event):
    """Is this event BTN_TOOL_DOUBLETAP?

    Args:
      event: an MTB event

    Returns:
      True if this is a BTN_TOOL_DOUBLETAP event
    """
    return cls.IsKeyTypeWithCode(event, BTN_TOOL_DOUBLETAP)

  @classmethod
  def IsBtnToolTripletap(cls, event):
    """Is this event BTN_TOOL_TRIPLETAP?

    Args:
      event: an MTB event

    Returns:
      True if this is a BTN_TOOL_TRIPLETAP event
    """
    return cls.IsKeyTypeWithCode(event, BTN_TOOL_TRIPLETAP)

  @classmethod
  def IsBtnToolQuadtap(cls, event):
    """Is this event BTN_TOOL_QUADTAP?

    Args:
      event: an MTB event

    Returns:
      True if this is a BTN_TOOL_QUADTAP event
    """
    return cls.IsKeyTypeWithCode(event, BTN_TOOL_QUADTAP)

  @classmethod
  def IsBtnToolQuinttap(cls, event):
    """Is this event BTN_TOOL_QUINTTAP?

    Args:
      event: an MTB event

    Returns:
      True if this is a BTN_TOOL_QUINTTAP event
    """
    return cls.IsKeyTypeWithCode(event, BTN_TOOL_QUINTTAP)

  @classmethod
  def IsBtnTouch(cls, event):
    """Is this event BTN_TOUCH?

    Args:
      event: an MTB event

    Returns:
      True if this is a BTN_TOUCH event
    """
    return cls.IsKeyTypeWithCode(event, BTN_TOUCH)

  @classmethod
  def IsSynReport(cls, event):
    """Determine if this event is SYN_REPORT.

    Args:
      event: an MTB event

    Returns:
      True if this is a SYN_REPORT event
    """
    return bool(event.get(MTB.SYN_REPORT, False))


class MtbStateMachine:
  """The state machine for MTB events.

  It traces the slots, tracking IDs, x coordinates, y coordinates, etc. If
  these values are not changed explicitly, the values are kept across events.

  Note that the kernel driver only reports what is changed. Due to its
  internal state machine, it is possible that either x or y in
  self._point[tid] is None initially even the instance has been created.
  """
  def __init__(self):
    self._tid = None
    # Set the default slot to 0 as it may not be displayed in the MTB events
    self._slot = 0
    # Some abnormal event files may not display the tracking ID in the
    # beginning. To handle this situation, we need to initialize
    # the following variables:  _slot_to_tid, _point
    #
    # As an example, refer to the following event file which is one of
    # the golden samples with this problem.
    #   testdata/touch_data/stationary_finger_shift_with_2nd_finger_tap.dat
    self._slot_to_tid = {self._slot: self._tid}
    self._point = {self._tid: Point()}
    self._pressure = {self._tid: None}
    self._syn_time = None
    self._number_fingers = 0
    self._leaving_slots = []

  def _DeleteLeavingSlots(self):
    """Delete the leaving slots. Remove the slots and their tracking IDs."""
    for slot in self._leaving_slots:
      del self._slot_to_tid[slot]
      self._number_fingers -= 1
    self._leaving_slots = []

  def AddEvent(self, event):
    """Update the internal states with the event.

    Args:
      event: an MTB event
    """

    # Switch the slot.
    if MtbEvent.IsAbsMtSlot(event):
      self._slot = event[MTB.EV_VALUE]

    # Get a new tracking ID.
    elif MtbEvent.IsNewContact(event):
      self._tid = event[MTB.EV_VALUE]
      self._slot_to_tid[self._slot] = self._tid
      self._point[self._tid] = Point()
      self._number_fingers += 1

    # A slot is leaving.
    # Do not delete this slot until this last packet is reported.
    elif MtbEvent.IsFingerLeaving(event):
      self._leaving_slots.append(self._slot)

    # Update x value.
    elif MtbEvent.IsAbsMtPositionX(event):
      self._point[self._slot_to_tid[self._slot]].x = event[MTB.EV_VALUE]

    # Update y value.
    elif MtbEvent.IsAbsMtPositionY(event):
      self._point[self._slot_to_tid[self._slot]].y = event[MTB.EV_VALUE]

    # Update z value (pressure)
    elif MtbEvent.IsAbsMtPressure(event):
      self._pressure[self._slot_to_tid[self._slot]] = event[MTB.EV_VALUE]

    # Use the SYN_REPORT time as the packet time
    elif MtbEvent.IsSynReport(event):
      self._syn_time = event[MTB.EV_TIME]

  def GetCurrentTidDataForAllTids(self, request_data_ready=True):
    """Gets current packet's tid data.

    The current tid data includes the point, the pressure, and the syn_time
    for all tids.

    Args:
      request_data_ready: if set to true, it will not output current_tid_data
          until all data including x, y, pressure, syn_time, etc. in the packet
          have been assigned.

    Returns:
      a sorted list of tuples (tid, slot, tid_packet)
    """
    current_tid_data = []
    for slot, tid in self._slot_to_tid.items():
      point = copy.deepcopy(self._point.get(tid))
      pressure = self._pressure.get(tid)
      # Check if all attributes are non-None values.
      # Note: we cannot use
      #           all([all(point.Value()), pressure, self._syn_time])
      #       E.g., for a point = (0, 300), it will return False
      #       which is not what we want. We want it to return False
      #       only when there are None values.
      data_ready = all(map(lambda e: e is not None,
                       list(point.Value()) + [pressure, self._syn_time]))

      if (not request_data_ready) or data_ready:
        tid_packet = TidPacket(self._syn_time, point, pressure)
      else:
        tid_packet = None
      # Even tid_packet is None, we would like to report this tid so that
      # its client function GetOrderedFingerPaths() could construct
      # an ordered dictionary correctly based on the tracking ID.
      current_tid_data.append((tid, slot, tid_packet))

    self._DeleteLeavingSlots()
    return sorted(current_tid_data)


class Mtb:
  """An MTB class providing MTB format related utility methods."""

  def __init__(self, device=None, packets=None):
    self.device = device
    self.packets = packets

  def GetNumberContacts(self):
    """Gets the number of contacts (Tracking IDs)."""
    num_contacts = 0
    for packet in self.packets:
      for event in packet:
        if MtbEvent.IsNewContact(event):
          num_contacts += 1
    return num_contacts

  def GetOrderedFingerPaths(self, request_data_ready=True):
    """Constructs the finger paths ordered by occurrences of finger contacts.

    The finger_paths mapping the tid to its finger_path looks like
        {tid1: finger_path1,
         tid2: finger_path2,
         ...
        }
    where every tid represents a finger.

    A finger_path effectively consists of a list of tid_packets of the same
    tid in the event file. An example of its structure looks like
    finger_path:
        slot=0
        tid_packets = [tid_packet0, tid_packet1, tid_packet2, ...]

    A tid_packet looks like
        [100021.342104,         # syn_time
         (66, 100),             # point
         56,                    # pressure
         ...                    # maybe more attributes added later.
        ]

    This method is applicable when fingers are contacting and leaving
    the touch device continuously. The same slot number, e.g., slot 0 or
    slot 1, may be used for multiple times.

    Note that the finger contact starts at 0. The finger contacts look to
    be equal to the slot numbers in practice. However, this assumption
    seems not enforced in any document. For safety, we use the ordered
    finger paths dict here to guarantee that we could access the ith finger
    contact path data correctly.

    Also note that we do not sort finger paths by tracking IDs to derive
    the ordered dict because tracking IDs may wrap around.

    Args:
      request_data_ready: if set to true, it will not output the tid_data in a
          packet until all data including x, y, pressure, syn_time, etc. in the
          packet have been assigned.

    Returns:
      ordered_finger_paths_dict is an ordered dictionary of {tid: FingerPath}
    """
    ordered_finger_paths_dict = OrderedDict()
    state_machine = MtbStateMachine()
    for packet in self.packets:
      # Inject events into the state machine to update its state.
      for event in packet:
        state_machine.AddEvent(event)

      # If there are N fingers (tids) in a packet, we will have
      # N tid_packet's in the current packet. The loop below is to
      # append every tid_packet into its corresponding finger_path for
      # every tracking id in the current packet.
      for tid, slot, tid_packet in state_machine.GetCurrentTidDataForAllTids(
          request_data_ready):
        finger_path = ordered_finger_paths_dict.setdefault(tid,
                                                           FingerPath(slot, []))
        if tid_packet:
          finger_path.tid_packets.append(tid_packet)

    return ordered_finger_paths_dict

  def GetOrderedFingerPath(self, finger, attr):
    """Extracts the specified attribute from packets of the ith finger contact.

    Args:
      finger: the ith finger contact
      attr: an attribute in a tid packet which could be either 'point',
          'pressure', or 'syn_time'

    Returns:
      the list of the specified attribute in the specified finger path.
    """
    # finger_paths is a list ordered by the occurrences of finger contacts
    finger_paths = self.GetOrderedFingerPaths().values()
    if 0 <= finger < len(finger_paths):
      finger_path = finger_paths[finger]
      return finger_path.get(attr)
    return []

  def GetSlotData(self, slot, attr):
    """Extract the attribute data of the specified slot.

    Args:
        attr: an attribute in a tid packet which could be either 'point',
            'pressure', or 'syn_time'
    """
    for finger_path in self.GetOrderedFingerPaths().values():
      if finger_path.slot == slot:
        return finger_path.get(attr)
    return []

  def GetListSynTime(self, finger):
    """Get the list of syn_time instants from the packets of the ith finger
    contact if finger is not None. Otherwise, use all packets.

    Args:
      finger: the specified ith finger contact.
          If a finger contact is specified, extract only the list of
          syn_time from this finger contact.
          Otherwise, when the finger contact is set to None, take all
          packets into account. Note that the finger contact number
          starts from 0.

    Returns:
      the list of SYN_REPORT time instants in a specified finger contact
      if finger is specified; otherwise, return all SYN_REPORT time instants
    """
    if isinstance(finger, int):
      return self.GetOrderedFingerPath(finger, 'syn_time')
    else:
      # Note: the last event in a packet, represented as packet[-1], is
      #       'SYN_REPORT' of which the event time is the 'syn_time'.
      return [packet[-1].get(MTB.EV_TIME) for packet in self.packets]


class MtbParser:
  """Touch device MTB event Parser."""

  def __init__(self):
    """Constructs the regular expression search pattern of MTB events.

    An ordinary event looks like
      Event: time 133082.748019, type 3 (EV_ABS), code 0 (ABS_X), value 316

    A SYN_REPORT event looks like
      Event: time 10788.289613, -------------- SYN_REPORT ------------
    """
    # Get the pattern of an ordinary event
    ev_pattern_time = 'Event:\s*time\s*(\d+\.\d+)'
    ev_pattern_type = 'type\s*(\d+)\s*\(\w+\)'
    ev_pattern_code = 'code\s*(\d+)\s*\(\w+\)'
    ev_pattern_value = 'value\s*(-?\d+)'
    ev_sep = ',\s*'
    ev_pattern = ev_sep.join([ev_pattern_time, ev_pattern_type,
                              ev_pattern_code, ev_pattern_value])
    self._ev_pattern = re.compile(ev_pattern, re.I)

    # Get the pattern of the SYN_REPORT event
    ev_pattern_type_SYN_REPORT = '-+\s*SYN_REPORT\s-+'
    ev_pattern_SYN_REPORT = ev_sep.join([ev_pattern_time,
                                         ev_pattern_type_SYN_REPORT])
    self._ev_pattern_SYN_REPORT = re.compile(ev_pattern_SYN_REPORT, re.I)

  def _GetEventDictOrdinary(self, line):
    """Constructs the event dictionary for an ordinary event.

    Args:
      line: a line in the evtest output

    Returns:
      the event dict parsed from the line
    """
    result = self._ev_pattern.search(line)
    ev_dict = {}
    if result is not None:
      ev_dict[MTB.EV_TIME] = float(result.group(1))
      ev_dict[MTB.EV_TYPE] = int(result.group(2))
      ev_dict[MTB.EV_CODE] = int(result.group(3))
      ev_dict[MTB.EV_VALUE] = int(result.group(4))
    return ev_dict

  def _GetEventDictSynReport(self, line):
    """Constructs the event dictionary for a SYN_REPORT event.

    Args:
      line: a line in the evtest output

    Returns:
      the event dict parsed from the line
    """
    result = self._ev_pattern_SYN_REPORT.search(line)
    ev_dict = {}
    if result is not None:
      ev_dict[MTB.EV_TIME] = float(result.group(1))
      ev_dict[MTB.SYN_REPORT] = True
    return ev_dict

  def _GetEventDict(self, line):
    """Constructs the event dictionary.

    Args:
      line: a line in the evtest output

    Returns:
      the event dict parsed from the line
    """
    return (self._GetEventDictOrdinary(line) or
            self._GetEventDictSynReport(line) or False)

  def _IsSynReport(self, ev_dict):
    """Determines if this event is SYN_REPORT.

    Args:
      ev_dict: an event dict

    Returns:
      True if this is a SYN_REPORT event dict
    """
    return bool(ev_dict.get(MTB.SYN_REPORT))

  def Parse(self, raw_events):
    """Parse the raw event string into a list of event dictionary.

    Args:
      raw_events: evtest raw events

    Returns:
      a list of packets
    """
    ev_list = []
    # A packet is a list of events ended by SYN_REPORT.
    packets = []
    start_flag = False
    for line in raw_events:
      ev_dict = self._GetEventDict(line)
      if ev_dict:
        start_flag = True
        ev_list.append(ev_dict)
        if self._IsSynReport(ev_dict):
          packets.append(ev_list)
          ev_list = []
      elif start_flag:
        logging.warning('  Warning: format problem in event:\n  %s', line)
    return packets

  def ParseFile(self, filename):
    """Parse raw device events in the given file name.

    Args:
      filename: the full-path file output by evtest or mtplot

    Returns:
      a list of packets
    """
    packets = None
    if os.path.isfile(filename):
      with open(filename) as f:
        packets = self.Parse(f)
    return packets
