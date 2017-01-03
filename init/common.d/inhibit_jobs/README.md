ChromeOS Factory Software: Inhibit Upstart Jobs
===============================================
To inhibit an Upstart job (`/etc/init/*.conf`) from execution, add a file using
job name and describe why we want to disable it as file content.

To start these jobs, execute

    run_inhibited_job <JOBNAME>

If you want to do something else when the job was fired (and inhibited), for
example emitting another Upstart event so pending jobs can continue, create the
file as shell script with execution permission.

Examples
--------
To stop `powerd`, create a file `powerd` with following contents:

    In factory environment, we need to disable powerd so run-in tests (and many
    non-interactive tests) will not fall into suspended mode.  Also we need to
    disable powerd to access power button (and being able to close lid).


To start `powerd` maually, do:

    run_inhibited_job powerd


If you want all jobs pending on `powerd` to run, enable it for execution (
`chmod +x powerd`) and change its contents to:

    ```sh
    #!/bin/sh
    initctl emit -n started JOB=powerd
    ```
