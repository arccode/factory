ChromeOS Factory Software: Python Source
========================================
This folder contains manufacturing software and related tools in Python.

Standalone Projects
-------------------
 - `dkps/`: Device Key Provisioning Server.
 - [`dome/`](dome/README.md): Factory server management console.
 - `instalog/`: The log pipeline solution.
 - `testlog/`: The log format.
 - [`umpire/`](umpire/README.md): Unified server to integrate factory imaging
    and various services.

Shared and misc folders
-----------------------
 - [`config/`](config/README.md): Build time JSON configuration (see
    `utils/json_config.py`)
 - `doc/`: Templates and resources for document generation.
 - `experimental/`: Experimental programs.
 - `proto/`: Generated python code to access protobuf data.
 - [`tools/`](tools/README.md): Misc tool programs.
 - [`utils/`](utils/README.md): Utility programs shared by all modules and
    projects.
 - [`external`](external/README.md): Optional external libraries.

Manufacturing and testing
-------------------------
 - `goofy/`: The flow control and web user interface for factory software.
 - [`gooftool/`](gooftool/README.md): Google Factory Tool that provide ChromeOS
    finalization.
 - [`hwid/`](hwid/README.md): The Hardware Identifier tools for ChromeOS.
 - [`shopfloor/`](shopfloor/README.md): The interface to serve between ChromeOS
    factory software and partner shopfloor servers.
 - `device/`: Device-Aware API.
 - `test/`: Manufacturing tests, including:
   - `pytests/`: Individual test items to be defined in test list.
   - [`test_lists/`](test/test_lists/README.md): Test lists read by Goofy to
      control test flow and options.
