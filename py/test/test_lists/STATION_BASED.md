Station-Based Testing
=====================

"Station-based testing" is running Goofy on a fixture, and perform tests to
DUT (device under test).  (Usually, Goofy is run by the DUT itself.)  This is
useful for testing:

* Headless devices
* Low-end devices
* Non-chromeos devices which Goofy cannot run on it directly

`station_based.test_list.json` is a base test list for station based test.  You
can use it as an example, customize it to fit your requirement.

Useful Concepts
===============

Usually, a station-based test list contains the following parts:

* Station Setup: Only need to run once when device boots up, for example,

  - Setup network connection
  - Initialize third party fixture

  Override **StationSetupItems** in your test list to meet your requirement.

* Station Test Loop: An infinite loop that will run forever, including the
    following parts:

  - StationLoopStart: Preparation tasks for each DUT.

    - **StationLoopItemsBeforeConnection**: These will be run before device is
        connected.
    - ConnectDevice: Ask and wait for device connection.
    - **FactoryStateSetup**: Setup `FactoryState` of station.

  - **StationLoopMain**: Test items for each DUT.
  - StationLoopEnd: Clean up.

    - **FactoryStateCleanup**: Cleanup `FactoryState` of station.
    - DisconnectDevice: Ask and wait for device disconnection.
    - **StationLoopItemsAfterDisconnection**: These will be run after device is
        disconnected.

  Place your test items into **StationLoopMain**, and optionally customize
  **StationLoopItemsBeforeConnection** or **StationLoopItemsAfterDisconnection**
  if extra tasks need to be done at those time point.  If your device is not
  running Goofy (or be more specific, the `FactoryState` server), you can
  override **FactoryStateSetup** and **FactoryStateCleanup** to stop copying
  state from / to DUT.
