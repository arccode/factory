# Copyright 2018 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Handles /webapps/download_slots requests.

According to DUT (device under test) info embedded in request header, either it
will assign a new UUID to present a unique session if no uuid cookie presented
or keep a session alive mapped from the UUID in cookie. On the other hand, one
more information - N_PLACE will be returned which indicates whether the DUT gets
available download session (N_PLACE: 0) or been put in the queue due to slots
are all occupied already (ex: "N_PLACE: 3" shows that two DUTs are waiting for
the slot in front of it). In the end, the cookie of drop_slot would indicate
that this session is done so the slot can be reclaimed for other session.
"""

import collections
import logging
import time
import uuid

from twisted.internet import reactor


_SLOTS_NUMBER = 10
# Expects that client side will send heart beat in every 60 seconds
_SLOT_ALIVE_TIME = 80.0


class DownloadSlotsManager:
  """Download Slots Manager

  DownloadSlotsManager is responsible for keeping a fixed number of DUTs can get
  the slot. And only DUTs got slots can start to download resources from factory
  server.

  This class will also monitor whether there are any slots owned by dead DUTs so
  we can prevent slots from always being occupied. This is achieved by asking
  DUTs to send heartbeat constantly in order to keep it's own slot alive.

  Properties:
    slots: A dict to record slots allocated status. The key is UUID and the
           value is timestamp when requested or re-newed by heartbeat.
    wait_queue: If all slots are occupied already then DUTs requesting slots
                would be put into this OrderedDict and once available slot is
                released the DUT in head of OrderedDict will have priority to
                own.
    delayed_call: An object works as a timer in order to check expired slots.
    max_slots_num: The maximum slots number is defined to limit how many DUTs
                   can download resources in parallel.
  """
  def __init__(self):
    self.slots = {}
    self.wait_queue = collections.OrderedDict()
    self.delayed_call = None
    # TODO(marcochen): Support this variable to get value from umpire config and
    # be configured from DOME by users.
    self.max_slots_num = _SLOTS_NUMBER

  def _CheckRequestParameters(self, identity, drop_slot):
    if identity:
      if identity not in self.slots and identity not in self.wait_queue:
        logging.error('Identity - %s is shown but is unknown.', identity)
        return False
    elif drop_slot:
      logging.error('Request to drop a slot but without any identity.')
      return False
    return True

  def _TryToRequestSlot(self):
    identity = str(uuid.uuid1())
    now = time.time()

    if len(self.slots) + len(self.wait_queue) < self.max_slots_num:
      self.slots[identity] = now
      logging.debug('Slot is requested and identity is %s.', identity)

      self._PrepareTimerForDeadSlot()

      return (identity, 0)

    # All slots are occupied already so need to be put into queue.
    self.wait_queue[identity] = now
    place = len(self.wait_queue)
    logging.debug('Slots are all occupied so need to wait in %d place.', place)

    return (identity, place)

  def _DropOccupiedSlot(self, identity):
    if identity in self.slots:
      del self.slots[identity]
    else:
      del self.wait_queue[identity]

    logging.debug('One slot is available now from %s.', identity)
    self._CheckAvailableSlot()

    return (identity, -1)

  def _HeartBeat(self, identity):
    now = time.time()
    if identity in self.slots:
      self.slots[identity] = now
      place = 0
    else:
      self.wait_queue[identity] = now
      place = list(self.wait_queue).index(identity) + 1
    return (identity, place)

  def _CheckAvailableSlot(self):
    if len(self.slots) >= self.max_slots_num or not self.wait_queue:
      return

    # available slot is ready now.
    available_slots = self.max_slots_num - len(self.slots)
    while available_slots > 0 and self.wait_queue:
      identity, timestamp = self.wait_queue.popitem(last=False)
      self.slots[identity] = timestamp
      available_slots -= 1
      logging.debug('Congrats! available slot is ready for %s.', identity)

  def ProcessSlotRequest(self, dut_info):
    identity = dut_info.get('uuid')
    drop_slot = 'drop_slot' in dut_info

    # do error handling first.
    if not self._CheckRequestParameters(identity, drop_slot):
      return None

    # start to process the request.
    if not identity:
      result = self._TryToRequestSlot()
    elif drop_slot:
      result = self._DropOccupiedSlot(identity)
    else:
      result = self._HeartBeat(identity)

    return 'UUID: %s\nN_PLACE: %d\n' % result

  def _RemoveExpiredSession(self):
    now = time.time()
    self.slots = {identity: t for identity, t in self.slots.items()
                  if now - t < _SLOT_ALIVE_TIME}
    self.wait_queue = collections.OrderedDict(
        (identity, t) for identity, t in self.wait_queue.items()
        if now - t < _SLOT_ALIVE_TIME)
    self._CheckAvailableSlot()

  def _PrepareTimerForDeadSlot(self, timeout=_SLOT_ALIVE_TIME):
    if self.delayed_call is None:
      self.delayed_call = reactor.callLater(timeout, self._SlotTimeOutFunc)
      logging.debug('Timer is up.')

  def _SlotTimeOutFunc(self):
    logging.debug('Timer is fired to check slots which are expired.')
    self.delayed_call = None
    self._RemoveExpiredSession()

    if not self.slots and not self.wait_queue:
      logging.debug('No timer is fired.')
      return

    # Fire another timer for oldest slot now.
    joined_dict = self.slots.copy()
    joined_dict.update(self.wait_queue)
    oldest_slot = min(joined_dict, key=joined_dict.get)
    next_time = _SLOT_ALIVE_TIME - (time.time() - joined_dict[oldest_slot]) + 1
    self._PrepareTimerForDeadSlot(next_time)
    logging.debug('Another timer is up for slot - %s', oldest_slot)
