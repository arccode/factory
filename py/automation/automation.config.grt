# Test automation config for Google Required Test
#
# This is a python dictionary object, map from test_path to a tuple
# Tests that are not in this file will be skipped.
# In the tuple there are the arguments for controlling the test:
#   time_out (sec): the test will be stopped after time_out
#   input string to browser: Input string to browser are like 'hello world\n'
#   input keys using ectool: Input keys using ectool are like 'hello world<enter>'
#   custom function: Custom functions can also be used,
#     like custom_function/FATP_factory_Finalize.py

{
  'FATP.Start':
    (10, 'SERIAL_NUMBER\n',),
  'FATP.factory_VPD':
    (60,),
  'FATP.Hwid':
    (60,),
  'FATP.Finalize':
    (300, 'f',),
}
