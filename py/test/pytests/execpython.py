
import logging
import unittest

class ExecPythonTest(unittest.TestCase):
    '''A simple test that just executes a Python script.

    Args:
        script: The Python code to execute.
    '''
    def runTest(self):
        script = self.test_info.args['script']
        logging.info("Executing Python script: '''%s'''", script)
        exec script in {'test_info': self.test_info}, {}
        logging.info("Script succeeded")
