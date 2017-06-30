Factory Server and Shopfloor Service
====================================

Overview
--------

To help integration with manufacturing line shopfloor backend systems, the
concept of "Factory Server" and
`
"`Shopfloor Service <https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/shopfloor/README.md>`_"
is introduced.

For legacy projects, the
:py:class:`cros.factory.shopfloor.factory_server.FactoryServer` class
implements common base to support various factory server, shopfloor, and product
requirements.

For new projects, please try the new factory server
"`Umpire <https://chromium.googlesource.com/chromiumos/platform/factory/+/master/py/umpire/README.md>`_".

Shopfloor Service API
---------------------

.. py:module:: cros.factory.shopfloor.shopfloor_service

.. autoclass:: ShopfloorService
   :members:

Legacy Factory Server
---------------------

.. py:module:: cros.factory.shopfloor.factory_server

.. autoclass:: FactoryServer
   :members:
