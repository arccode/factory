ChromeOS Factory Software: Inhibit Upstart Jobs
===============================================
To inhibit an Upstart job (`/etc/init/*.conf`) from execution, add a file using
job name and describe why we want to disable it as file content. The job will be
disabled by `/usr/share/cros/factory_utils.sh`.

To start these jobs, execute

    run_inhibited_job <JOBNAME>

Examples
--------
To stop `powerd`, create a file `powerd` with following contents:

    In factory environment, we need to disable powerd so run-in tests (and many
    non-interactive tests) will not fall into suspended mode.  Also we need to
    disable powerd to access power button (and being able to close lid).


To start `powerd` maually, do:

    run_inhibited_job powerd
