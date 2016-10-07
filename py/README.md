ChromeOS Factory Software: Python Source
========================================
This folder contains manufacturing software and related tools in Python.

Standalone Projects
-------------------
 - `dkps/`: Device Key Provisioning Server.
 - `dome/`: Factory server management console.
 - `instalog/`: The log pipeline solution.
 - `factory_flow/`: Automated testing of factory flow.
 - `lumberjack/`: A log processing tool.
 - `minijack/`: A console and dashboard for manufacturing status.
 - `umpire/`: Unified server to integrate factory imaging and various services.

Shared and misc folders
-----------------------
 - `config/`: Build time JSON configuration (see `utils/json_config.py`)
 - `doc/`: Templates and resources for document generation.
 - `experimental/`: Experimental programs.
 - `proto/`: Generated python code to access protobuf data.
 - `tools/`: Misc tool programs.
 - `utils/`: Utility programs shared by all modules and projects.

Manufacturing and testing
-------------------------
 - `goofy/`: The flow control and web user interface for factory software.
 - `gooftool/`: Google Factory Tool that provide ChromeOS finalization.
 - `hwid/`: The Hardware Identifier tools for ChromeOS.
 - `shopfloor/`: The interface to serve between ChromeOS factory software and
   partner shopfloor servers.
 - `device/`: Device-Aware API.
 - `test/`: Manufacturing tests, including:
   - `pytests/`: Individual test items to be defined in test list.
   - `test_lists/`: Test lists read by Goofy to control test flow and options.
