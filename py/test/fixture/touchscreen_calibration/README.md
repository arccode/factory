Touchscreen Calibration
=======================

The touchscreen calibration test fixture uses an arduino DUE board to
control the motor and sensors. Here we describe how to set up the
proper environment to flash the firmware to the arduino board.
It would be convenient to use a chromebook machine as the factory
control host and also for working on the arduino code. Let's use
the x86 specific platform, e.g., Link, as an example. Before being able
to run arduino IDE, you need to setup Java Runtime Environment first.

Setup of the Java Runtime Environment
-------------------------------------

  The arduino IDE requires the JRE which could be downloaded from:
  https://www.java.com/en/download/help/linux_x64_install.xml

  This is for Linux 64-bit OS. I have been working the arduino IDE with
  jre1.7.0_51 nicely. You could untar the tarball on your host, and
  then scp the folder to the chromebook machine.

  On your host:

    $ tar zxvf jre-7u51-linux-x64.tar.gz

  On the chromebook machine:

    $ mkdir /usr/local/java

  On your host:

    $ scp -r jre1.7.0_51 $CHROMEBOOK_IP:/usr/local/java

  On the chromebook machine:

    $ export PATH=$PATH:/usr/local/java/jre1.7.0_51/bin


Setup of the arduino IDE on a Chromebook test image
---------------------------------------------------

  The arduino IDE could be downloaded from the web page:
  http://arduino.cc/en/main/software

  Note that to work with the arduino DUE, the IDE version may be higher
  than that for the most common arduino UNO board. In this project, we
  use arduino-1.5.6-r2 BETA version.

  Place the arduino folder under `/usr/local/arduino`

  To launch arduino IDE:

    $ mount -o remount,rw /
    $ cd /usr/local/arduino/arduino-1.5.6-r2
    $ sudo ./arduino

Installation of the DueTimer library
------------------------------------

  The arduino code uses the 3rd party library, DueTimer, to control the
  timer interrupt. The version used is DueTimer-1.4.1 and the tarball
  could be found in:
  https://github.com/ivanseidel/DueTimer

  If you login as a root, the `Arduino` folder and its subdirectories
  will be created under `/root` automatically. Install DueTimer in
  `/root/Arduino/libraries/DueTimer`.

Misc notes
----------

 - The preference is located under

       ~/.arduino/preferences.txt # for UNO, or
       ~/.arduino15/preferences.txt # for DUE

   You could edit the preference file to manipulate the IDE window
   geometry and the font size.

 - We need some 32-bit libraries for running the toolchains on x86-64
   platform. Specifically, `arm-non-eabi-g++` is used as a cross compiler
   for arduino DUE. If the required 32-bit libraries are missing, you
   may get an error like

       bash: ./arm-non-eabi-g++: No such file or directory

   Check the OS on a Link which is x86_64:

       $ uname -a
       Linux localhost 3.8.11 #1 SMP Wed Oct 23 23:24:07 PDT 2013 x86_64 ...

   Locate thr cross compiler:

       $ find . | grep arm-none-eabi-g++
       ./arduino-1.5.6-r2/hardware/tools/g++_arm_none_eabi/bin/arm-none-eabi-g++

   The cross compiler is a 32-bit executable.

       $ cd arduino-1.5.6-r2/hardware/tools/g++_arm_none_eabi/bin
       $ file arm-none-eabi-g++
       arm-none-eabi-g++: ELF 32-bit LSB executable, Intel 80386, version 1 ...

   Look up the shared library dependencies, and find what are missing.

       $ ldd arm-none-eabi-g++
       linux-gate.so.1 =>  (0xf77b6000)
       libc.so.6 => /lib/libc.so.6 ()
       /lib/ld-linux.so.2 ()

   You need to scp any missing .so files from your host to the machine,
   i.e., `libc.so.6` and `ld-linux.so.2` in this case.

   On your host:

       $ cd /lib
       $ scp ld-linux.so.2 $CHROMEBOOK_IP:/lib/
       $ scp libc.so.6 $CHROMEBOOK_IP:/lib/

 - Sometimes you got `SAM-BA operation failed` when flashing the firmware.
   You need to reset the board by unplugging the USB cable and turn off
   the fixture power. And then reconnect the USB cable to flash the
   firmware.
