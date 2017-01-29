# Copyright 2017 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Socket plugin common file.

Transfers events via custom protocol over raw socket.

Protocol definition:
  SEPARATOR := '\0'
  DATA := any character
  INT := [0-9]+ <SEPARATOR>
  SIZE := <INT> cast to integer
  COUNT := <INT> cast to integer
  CHECKSUM := <DATA>{32} <SEPARATOR>
  ATTACHMENT := <SIZE> <DATA>{<SIZE>} <CHECKSUM>
  ATTACHMENTS := <COUNT> <ATTACHMENT>{<COUNT>}
  EVENT := <SIZE> <DATA>{SIZE} <CHECKSUM> <ATTACHMENTS>
  CONFIRM := '1'
  SUCCESS_FAILURE := '0' or '1'

  REQUEST_1 := <COUNT> <EVENT>{COUNT}
  RESPONSE_1 := <CONFIRM> (syn: data-received)
  REQUEST_2 := <CONFIRM> (ack: request-emit)
  RESPONSE_2 := <SUCCESS_FAILURE> (syn-ack: emit-success)

Note the final syn/ack/syn-ack sequence.  This is important to prevent the
output plugin from timing out before receiving confirmation of the input
plugin successfully emitting the events, which results in the same batch of
events being sent multiple times.
"""

DEFAULT_PORT = 8893
SOCKET_TIMEOUT = 30
SEPARATOR = '\0'
CHUNK_SIZE = 1024

PING_RESPONSE = '1'
DATA_RECEIVED_CHAR = '1'
REQUEST_EMIT_CHAR = '1'
EMIT_SUCCESS_CHAR = '1'
