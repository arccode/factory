Factory Server and Shopfloor Service
====================================

Overview
--------

To help integration with manufacturing line shopfloor backend systems, we have
defined two server protocols.

One is "`Factory Server <https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/py/umpire/README.md>`_"
that every DUTs running Chrome OS Factory Software will directly connect to,
and the other is "`Shopfloor Service <https://chromium.googlesource.com/chromiumos/platform/factory/+/HEAD/py/shopfloor/README.md>`_"
that partner has to implement so the integration work is abstracted with
standardized interface.

Shopfloor Service API
---------------------

.. py:module:: shopfloor_service

.. autoclass:: ShopfloorService
   :members:

Factory Server API
---------------------

.. py:module:: cros.factory.umpire.server.rpc_dut

.. autoclass:: RootDUTCommands
   :members:

.. autoclass:: UmpireDUTCommands
   :members:

.. autoclass:: LogDUTCommands
   :members:
