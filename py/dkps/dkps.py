# Copyright 2015 The Chromium OS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""The DRM Keys Provisioning Server (DKPS) implementation."""

# TODO(littlecvr): Implement "without filter mode", which lets OEM encrypts DRM
#                  keys directly with ODM's public key, and the key server
#                  merely stores them without knowing anything about them.

from __future__ import print_function

import argparse
import hashlib
import imp
import json
import logging
import logging.config
import os
import shutil
import SimpleXMLRPCServer
import sqlite3
import textwrap

import gnupg
from six.moves import input


SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
FILTERS_DIR = os.path.join(SCRIPT_DIR, 'filters')
PARSERS_DIR = os.path.join(SCRIPT_DIR, 'parsers')
CREATE_DATABASE_SQL_FILE_PATH = os.path.join(
    SCRIPT_DIR, 'sql', 'create_database.sql')

DEFAULT_BIND_ADDR = '0.0.0.0'  # all addresses
DEFAULT_BIND_PORT = 5438

DEFAULT_DATABASE_FILE_NAME = 'dkps.db'
DEFAULT_GNUPG_DIR_NAME = 'gnupg'
DEFAULT_LOG_FILE_NAME = 'dkps.log'

DEFAULT_LOGGING_CONFIG = {
    'version': 1,
    'formatters': {
        'default': {
            'format': '%(asctime)s:%(levelname)s:%(funcName)s:'
                      '%(lineno)d:%(message)s'}},
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'formatter': 'default',
            'filename': DEFAULT_LOG_FILE_NAME,
            'maxBytes': 1024 * 1024,  # 1M
            'backupCount': 3},
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
            'stream': 'ext://sys.stdout'}},
    'root': {
        'level': 'INFO',
        # only log to file by default, but also log to console if invoked
        # directly from the command line
        'handlers': ['file'] + ['console'] if __name__ == '__main__' else []}}


class ProjectNotFoundException(ValueError):
  """Raised when no project was found in the database."""
  pass


class InvalidUploaderException(ValueError):
  """Raised when the signature of the uploader can't be verified."""
  pass


class InvalidRequesterException(ValueError):
  """Raised when the signature of the requester can't be verified."""
  pass


def GetSQLite3Connection(database_file_path):
  """Returns a tuple of SQLite3's (connection, cursor) to database_file_path.

  If the connection has been created before, it is returned directly. If it's
  not, this function creates the connection, ensures that the foreign key
  constraint is enabled, and returns.

  Args:
    database_file_path: path to the SQLite3 database file.
  """
  database_file_path = os.path.realpath(database_file_path)

  # Return if the connection to database_file_path has been created before.
  try:
    connection = GetSQLite3Connection.connection_dict[database_file_path]
    return (connection, connection.cursor())
  except KeyError:
    pass
  except AttributeError:
    GetSQLite3Connection.connection_dict = {}

  # Create connection.
  connection = sqlite3.connect(database_file_path)
  connection.row_factory = sqlite3.Row
  cursor = connection.cursor()

  # Enable foreign key constraint since SQLite3 disables it by default.
  cursor.execute('PRAGMA foreign_keys = ON')
  # Check if foreign key constraint is enabled.
  cursor.execute('PRAGMA foreign_keys')
  if cursor.fetchone()[0] != 1:
    raise RuntimeError('Failed to enable SQLite3 foreign key constraint')

  GetSQLite3Connection.connection_dict[database_file_path] = connection

  return (connection, cursor)


class DRMKeysProvisioningServer(object):
  """The DRM Keys Provisioning Server (DKPS) class."""

  def __init__(self, database_file_path, gnupg_homedir):
    """DKPS constructor.

    Args:
      database_file_path: path to the SQLite3 database file.
      gnupg_homedir: path to the GnuPG home directory.
    """
    self.database_file_path = database_file_path
    self.gnupg_homedir = gnupg_homedir

    if not os.path.isdir(self.gnupg_homedir):
      self.gpg = None
    else:
      self.gpg = gnupg.GPG(gnupghome=self.gnupg_homedir)

    if not os.path.isfile(self.database_file_path):
      self.db_connection, self.db_cursor = (None, None)
    else:
      self.db_connection, self.db_cursor = GetSQLite3Connection(
          self.database_file_path)

  def Initialize(self, gpg_gen_key_args_dict=None, server_key_file_path=None):
    """Creates the SQLite3 database and GnuPG home, and imports, or generates a
    GPG key for the server to use.

    Args:
      gpg_gen_key_args_dict: will be passed directly as the keyword arguments to
          python-gnupg's gen_key() function if server_key_file_path is None.
          Can be used to customize the key generator process, such as key_type,
          key_length, etc. See python-gnupg's doc for what can be customized.
      server_key_file_path: path to the server key to use. If not None, the
          system will simply import this key and use it as the server key; if
          None, the system will generate a new key.

    Raises:
      RuntimeError is the database and GnuPG home have already been initialized.
    """
    # Create GPG instance and database connection.
    self.gpg = gnupg.GPG(gnupghome=self.gnupg_homedir)
    self.db_connection, self.db_cursor = GetSQLite3Connection(
        self.database_file_path)

    # If any key exists, the system has already been initialized.
    if self.gpg.list_keys():
      raise RuntimeError('Already initialized')

    if server_key_file_path:  # use existing key
      # TODO(littlecvr): make sure the server key doesn't have passphrase.
      server_key_fingerprint, _ = self._ImportGPGKey(server_key_file_path)
    else:  # generate a new GPG key
      if gpg_gen_key_args_dict is None:
        gpg_gen_key_args_dict = {}
      if 'name_real' not in gpg_gen_key_args_dict:
        gpg_gen_key_args_dict['name_real'] = 'DKPS Server'
      if 'name_email' not in gpg_gen_key_args_dict:
        gpg_gen_key_args_dict['name_email'] = 'chromeos-factory-dkps@google.com'
      if 'name_comment' not in gpg_gen_key_args_dict:
        gpg_gen_key_args_dict['name_comment'] = 'DRM Keys Provisioning Server'
      key_input_data = self.gpg.gen_key_input(**gpg_gen_key_args_dict)
      server_key_fingerprint = self.gpg.gen_key(key_input_data).fingerprint

    # Create and set up the schema of the database.
    with open(CREATE_DATABASE_SQL_FILE_PATH) as f:
      create_database_sql = f.read()
    with self.db_connection:
      self.db_cursor.executescript(create_database_sql)

    # Record the server key fingerprint.
    with self.db_connection:
      self.db_cursor.execute(
          'INSERT INTO settings (key, value) VALUES (?, ?)',
          ('server_key_fingerprint', server_key_fingerprint))

  def Destroy(self):
    """Destroys the database and GnuPG home directory.

    This is the opposite of Initialize(). It essentially removes the SQLite3
    database file and GnuPG home directory.
    """
    # Remove database.
    if self.db_connection:
      self.db_connection.close()
    if os.path.exists(self.database_file_path):
      os.remove(self.database_file_path)

    # Remove GnuPG home.
    if self.gpg:
      self.gpg = None
    if os.path.exists(self.gnupg_homedir):
      shutil.rmtree(self.gnupg_homedir)

  def AddProject(self, name, uploader_key_file_path, requester_key_file_path,
                 parser_module_file_name, filter_module_file_name=None):
    """Adds a project.

    Args:
      name: name of the project, must be unique.
      uploader_key_file_path: path to the OEM's public key file.
      requester_key_file_path: path to the ODM's public key file.
      parser_module_file_name: file name of the parser python module.
      filter_module_file_name: file name of the filter python module.

    Raises:
      ValueError if either the uploader's or requester's key are imported (which
      means they are used by another project).
    """
    # Try to load the parser and filter modules.
    self._LoadParserModule(parser_module_file_name)
    if filter_module_file_name is not None:
      self._LoadFilterModule(filter_module_file_name)

    # Try to import uploader and requester keys and add project info into the
    # database, if failed at any step, delete imported keys.
    uploader_key_fingerprint, requester_key_fingerprint = (None, None)
    uploader_key_already_exists, requester_key_already_exists = (False, False)
    try:
      uploader_key_fingerprint, uploader_key_already_exists = (
          self._ImportGPGKey(uploader_key_file_path))
      if uploader_key_already_exists:
        raise ValueError('Uploader key already exists')
      requester_key_fingerprint, requester_key_already_exists = (
          self._ImportGPGKey(requester_key_file_path))
      if requester_key_already_exists:
        raise ValueError('Requester key already exists')
      with self.db_connection:
        self.db_cursor.execute(
            'INSERT INTO projects ('
            '    name, uploader_key_fingerprint, requester_key_fingerprint, '
            '    parser_module_file_name, filter_module_file_name) '
            'VALUES (?, ?, ?, ?, ?)',
            (name, uploader_key_fingerprint, requester_key_fingerprint,
             parser_module_file_name, filter_module_file_name))
    except BaseException:
      if not uploader_key_already_exists and uploader_key_fingerprint:
        self.gpg.delete_keys(uploader_key_fingerprint)
      if not requester_key_already_exists and requester_key_fingerprint:
        self.gpg.delete_keys(requester_key_fingerprint)
      raise

  def UpdateProject(self, name, uploader_key_file_path=None,
                    requester_key_file_path=None, filter_module_file_name=None):
    """Updates a project.

    Args:
      name: name of the project, must be unique.
      uploader_key_file_path: path to the OEM's public key file.
      requester_key_file_path: path to the ODM's public key file.
      filter_module_file_name: file name of the filter python module.

    Raises:
      RuntimeError if SQLite3 can't update the project row (for any reason).
    """
    # Try to load the filter module.
    if filter_module_file_name is not None:
      self._LoadFilterModule(filter_module_file_name)

    project = self._FetchProjectByName(name)

    # Try to import uploader and requester keys and add project info into the
    # database, if failed at any step, delete any newly imported keys.
    uploader_key_fingerprint, requester_key_fingerprint = (None, None)
    old_uploader_key_fingerprint = project['uploader_key_fingerprint']
    old_requester_key_fingerprint = project['requester_key_fingerprint']
    same_uploader_key, same_requester_key = (True, True)
    try:
      sql_set_clause_list = ['filter_module_file_name = ?']
      sql_parameters = [filter_module_file_name]

      if uploader_key_file_path:
        uploader_key_fingerprint, same_uploader_key = self._ImportGPGKey(
            uploader_key_file_path)
        sql_set_clause_list.append('uploader_key_fingerprint = ?')
        sql_parameters.append(uploader_key_fingerprint)

      if requester_key_file_path:
        requester_key_fingerprint, same_requester_key = self._ImportGPGKey(
            uploader_key_file_path)
        sql_set_clause_list.append('requester_key_fingerprint = ?')
        sql_parameters.append(requester_key_fingerprint)

      sql_set_clause = ','.join(sql_set_clause_list)
      sql_parameters.append(name)
      with self.db_connection:
        self.db_cursor.execute(
            'UPDATE projects SET %s WHERE name = ?' % sql_set_clause,
            tuple(sql_parameters))
      if self.db_cursor.rowcount != 1:
        raise RuntimeError('Failed to update project %s' % name)
    except BaseException:
      if not same_uploader_key and uploader_key_fingerprint:
        self.gpg.delete_keys(uploader_key_fingerprint)
      if not same_requester_key and requester_key_fingerprint:
        self.gpg.delete_keys(requester_key_fingerprint)
      raise

    if not same_uploader_key:
      self.gpg.delete_keys(old_uploader_key_fingerprint)
    if not same_requester_key:
      self.gpg.delete_keys(old_requester_key_fingerprint)

  def RemoveProject(self, name):
    """Removes a project.

    Args:
      name: the name of the project specified when added.
    """
    project = self._FetchProjectByName(name)

    self.gpg.delete_keys(project['uploader_key_fingerprint'])
    self.gpg.delete_keys(project['requester_key_fingerprint'])

    with self.db_connection:
      self.db_cursor.execute(
          'DELETE FROM drm_keys WHERE project_name = ?', (name,))
      self.db_cursor.execute('DELETE FROM projects WHERE name = ?', (name,))

  def ListProjects(self):
    """Lists all projects."""
    self.db_cursor.execute('SELECT * FROM projects ORDER BY name ASC')
    return self.db_cursor.fetchall()

  def Upload(self, encrypted_serialized_drm_keys):
    """Uploads a list of DRM keys to the server. This is an atomic operation. It
    will either succeed and save all the keys, or fail and save no keys.

    Args:
      encrypted_serialized_drm_keys: the serialized DRM keys signed by the
          uploader and encrypted by the server's public key.

    Raises:
      InvalidUploaderException if the signature of the uploader can not be
      verified.
    """
    decrypted_obj = self.gpg.decrypt(encrypted_serialized_drm_keys)
    project = self._FetchProjectByUploaderKeyFingerprint(
        decrypted_obj.fingerprint)
    serialized_drm_keys = decrypted_obj.data

    # Pass to the parse function.
    parser_module = self._LoadParserModule(project['parser_module_file_name'])
    drm_key_list = parser_module.Parse(serialized_drm_keys)

    drm_key_hash_list = []
    for drm_key in drm_key_list:
      drm_key_hash_list.append(hashlib.sha1(json.dumps(drm_key)).hexdigest())

    # Pass to the filter function if needed.
    if project['filter_module_file_name']:  # filter module can be null
      filter_module = self._LoadFilterModule(project['filter_module_file_name'])
      filtered_drm_key_list = filter_module.Filter(drm_key_list)
    else:
      # filter module is optional
      filtered_drm_key_list = drm_key_list

    # Fetch server key for signing.
    server_key_fingerprint = self._FetchServerKeyFingerprint()

    # Sign and encrypt each key by server's private key and requester's public
    # key, respectively.
    encrypted_serialized_drm_key_list = []
    requester_key_fingerprint = project['requester_key_fingerprint']
    for drm_key in filtered_drm_key_list:
      encrypted_obj = self.gpg.encrypt(
          json.dumps(drm_key), requester_key_fingerprint,
          always_trust=True, sign=server_key_fingerprint)
      encrypted_serialized_drm_key_list.append(encrypted_obj.data)

    # Insert into the database.
    with self.db_connection:
      self.db_cursor.executemany(
          'INSERT INTO drm_keys ('
          '    project_name, drm_key_hash, encrypted_drm_key) '
          'VALUES (?, ?, ?)',
          list(zip([project['name']] * len(encrypted_serialized_drm_key_list),
                   drm_key_hash_list, encrypted_serialized_drm_key_list)))

  def AvailableKeyCount(self, requester_signature):
    """Queries the number of remaining keys.

    Args:
      requester_signature: a message signed by the requester. Since the server
          doesn't need any additional info from the requester, the requester can
          simply sign a random string and send it here.

    Returns:
      The number of remaining keys that can be requested.

    Raises:
      InvalidRequesterException if the signature of the requester can not be
      verified.
    """
    verified = self.gpg.verify(requester_signature)
    if not verified:
      raise InvalidRequesterException(
          'Invalid requester, check your signing key')

    project = self._FetchProjectByRequesterKeyFingerprint(verified.fingerprint)

    self.db_cursor.execute(
        'SELECT COUNT(*) AS available_key_count FROM drm_keys '
        'WHERE project_name = ? AND device_serial_number IS NULL',
        (project['name'],))
    return self.db_cursor.fetchone()['available_key_count']

  def Request(self, encrypted_device_serial_number):
    """Requests a DRM key by device serial number.

    Args:
      encrypted_device_serial_number: the device serial number signed by the
          requester and encrypted by the server's public key.

    Raises:
      InvalidRequesterException if the signature of the requester can not be
      verified. RuntimeError if no available keys left in the database.
    """
    decrypted_obj = self.gpg.decrypt(encrypted_device_serial_number)
    project = self._FetchProjectByRequesterKeyFingerprint(
        decrypted_obj.fingerprint)
    device_serial_number = decrypted_obj.data

    def FetchDRMKeyByDeviceSerialNumber(project_name, device_serial_number):
      self.db_cursor.execute(
          'SELECT * FROM drm_keys WHERE project_name = ? AND '
          'device_serial_number = ?',
          (project_name, device_serial_number))
      return self.db_cursor.fetchone()

    row = FetchDRMKeyByDeviceSerialNumber(project['name'], device_serial_number)
    if row:  # the SN has already paired
      return row['encrypted_drm_key']

    # Find an unpaired key.
    with self.db_connection:
      # SQLite3 does not support using LIMIT clause in UPDATE statement by
      # default, unless SQLITE_ENABLE_UPDATE_DELETE_LIMIT flag is defined during
      # compilation. Since this script may be deployed on partner's computer,
      # we'd better assume they don't have this flag on.
      self.db_cursor.execute(
          'UPDATE drm_keys SET device_serial_number = ? '
          'WHERE id = (SELECT id FROM drm_keys WHERE project_name = ? AND '
          '            device_serial_number IS NULL LIMIT 1)',
          (device_serial_number, project['name']))
    if self.db_cursor.rowcount != 1:  # insufficient keys
      raise RuntimeError(
          'Insufficient DRM keys, ask for the OEM to upload more')

    row = FetchDRMKeyByDeviceSerialNumber(project['name'], device_serial_number)
    if row:
      return row['encrypted_drm_key']
    else:
      raise RuntimeError('Failed to find paired DRM key')

  def ListenForever(self, ip, port):
    """Starts the XML RPC server waiting for commands.

    Args:
      ip: IP to bind.
      port: port to bind.
    """
    class Server(SimpleXMLRPCServer.SimpleXMLRPCServer):
      def _dispatch(self, method, params):
        # Catch exceptions and log them. Without this, SimpleXMLRPCServer simply
        # output the error message to stdout, and we won't be able to see what
        # happened in the log file.
        logging.info('%s called', method)
        try:
          result = SimpleXMLRPCServer.SimpleXMLRPCServer._dispatch(
              self, method, params)
          return result
        except BaseException as e:
          logging.exception(e)
          raise

    server = Server((ip, port), allow_none=True)

    server.register_introspection_functions()
    server.register_function(self.AvailableKeyCount)
    server.register_function(self.Upload)
    server.register_function(self.Request)

    server.serve_forever()

  def _ImportGPGKey(self, key_file_path):
    """Imports a GPG key from a file.

    Args:
      key_file_path: path to the GPG key file.

    Returns:
      A tuple (key_fingerprint, key_already_exists). The 1st element is the
      imported key's fingerprint, and the 2nd element is True if the key was
      already in the database before importing, False otherwise.
    """
    with open(key_file_path) as f:
      import_results = self.gpg.import_keys(f.read())
    key_already_exists = (import_results.imported == 0)
    key_fingerprint = import_results.fingerprints[0]
    return (key_fingerprint, key_already_exists)

  def _LoadFilterModule(self, filter_module_file_name):
    """Loads the filter module.

    Args:
      filter_module_file_name: file name of the filter module in FILTERS_DIR.

    Returns:
      The loaded filter module on success.

    Raises:
      Exception if failed, see imp.load_source()'s doc for what could be raised.
    """
    return imp.load_source(
        'filter_module', os.path.join(FILTERS_DIR, filter_module_file_name))

  def _LoadParserModule(self, parser_module_file_name):
    """Loads the parser module.

    Args:
      parser_module_file_name: file name of the parser module in PARSERS_DIR.

    Returns:
      The loaded parser module on success.

    Raises:
      Exception if failed, see imp.load_source()'s doc for what could be raised.
    """
    return imp.load_source(
        'parser_module', os.path.join(PARSERS_DIR, parser_module_file_name))

  def _FetchServerKeyFingerprint(self):
    """Returns the server GPG key's fingerprint."""
    self.db_cursor.execute(
        "SELECT * FROM settings WHERE key = 'server_key_fingerprint'")
    row = self.db_cursor.fetchone()
    if not row:
      raise ValueError('Server key fingerprint not exists')
    return row['value']

  def _FetchOneProject(self, name=None,
                       uploader_key_fingerprint=None,
                       requester_key_fingerprint=None,
                       exception_type=None, error_msg=None):
    """Fetches the project by name, uploader key fingerprint, or requester key
    fingerprint.

    This function combines the name, uploader_key_fingerprint,
    requester_key_fingerprint conditions (if not None) with the AND operator,
    and tries to fetch one project from the database.

    Args:
      name: name of the project.
      uploader_key_fingerprint: uploader key fingerprint of the project.
      requester_key_fingerprint: requester key fingerprint of the project.
      exception_type: if no project was found and exception_type is not None,
          raise exception_type with error_msg.
      error_msg: if no project was found and exception_type is not None, raise
          exception_type with error_msg.

    Returns:
      A project that matches the name, uploader_key_fingerprint, and
      requester_key_fingerprint conditiions.

    Raises:
      exception_type with error_msg if not project was found.
    """
    # pylint: disable=unused-argument
    where_clause_list = []
    params = []
    local_vars = locals()
    for param_name in ['name', 'uploader_key_fingerprint',
                       'requester_key_fingerprint']:
      if local_vars[param_name] is not None:
        where_clause_list.append('%s = ?' % param_name)
        params.append(locals()[param_name])
    if not where_clause_list:
      raise ValueError('No conditions given to fetch the project')
    where_clause = 'WHERE ' + ' AND '.join(where_clause_list)

    self.db_cursor.execute(
        'SELECT * FROM projects %s' % where_clause, tuple(params))
    project = self.db_cursor.fetchone()

    if not project and exception_type:
      raise exception_type(error_msg)

    return project

  def _FetchProjectByName(self, name):
    return self._FetchOneProject(
        name=name, exception_type=ProjectNotFoundException,
        error_msg=('Project %s not found' % name))

  def _FetchProjectByUploaderKeyFingerprint(self, uploader_key_fingerprint):
    return self._FetchOneProject(
        uploader_key_fingerprint=uploader_key_fingerprint,
        exception_type=InvalidUploaderException,
        error_msg='Invalid uploader, check your signing key')

  def _FetchProjectByRequesterKeyFingerprint(self, requester_key_fingerprint):
    return self._FetchOneProject(
        requester_key_fingerprint=requester_key_fingerprint,
        exception_type=InvalidRequesterException,
        error_msg='Invalid requester, check your signing key')


def _ParseArguments():
  parser = argparse.ArgumentParser()
  parser.add_argument(
      '-d', '--database_file_path',
      default=os.path.join(SCRIPT_DIR, DEFAULT_DATABASE_FILE_NAME),
      help='path to the SQLite3 database file, default to "dkps.db" in the '
           'same directory of this script')
  parser.add_argument(
      '-g', '--gnupg_homedir',
      default=os.path.join(SCRIPT_DIR, DEFAULT_GNUPG_DIR_NAME),
      help='path to the GnuGP home directory, default to "gnupg" in the same '
           'directory of this script')
  parser.add_argument(
      '-l', '--log_file_path',
      default=os.path.join(SCRIPT_DIR, DEFAULT_LOG_FILE_NAME),
      help='path to the log file, default to "dkps.log" in the same directory '
           'of this script')
  subparsers = parser.add_subparsers(dest='command')

  parser_add = subparsers.add_parser('add', help='adds a new project')
  parser_add.add_argument('-n', '--name', required=True,
                          help='name of the new project')
  parser_add.add_argument('-u', '--uploader_key_file_path', required=True,
                          help="path to the uploader's public key file")
  parser_add.add_argument('-r', '--requester_key_file_path', required=True,
                          help="path to the requester's public key file")
  parser_add.add_argument('-p', '--parser_module_file_name', required=True,
                          help='file name of the parser module')
  parser_add.add_argument('-f', '--filter_module_file_name', default=None,
                          help='file name of the filter module')

  subparsers.add_parser('destroy', help='destroys the database')

  parser_update = subparsers.add_parser('update',
                                        help='updates an existing project')
  parser_update.add_argument('-n', '--name', required=True,
                             help='name of the project')
  parser_update.add_argument('-u', '--uploader_key_file_path', default=None,
                             help="path to the uploader's public key file")
  parser_update.add_argument('-r', '--requester_key_file_path', default=None,
                             help="path to the requester's public key file")
  parser_update.add_argument('-f', '--filter_module_file_name', default=None,
                             help='file name of the filter module')

  parser_init = subparsers.add_parser('init', help='initializes the database')
  parser_init.add_argument(
      '-g', '--gpg_gen_key_args', action='append', nargs=2, default={},
      help='arguments to use when generating GPG key for server')
  parser_init.add_argument(
      '-s', '--server_key_file_path', default=None,
      help="path to the server's private key file")

  subparsers.add_parser('list', help='lists all projects')

  parser_listen = subparsers.add_parser(
      'listen', help='starts the server, waiting for upload or request keys')
  parser_listen.add_argument(
      '--ip', default=DEFAULT_BIND_ADDR,
      help='IP to bind, default to %s' % DEFAULT_BIND_ADDR)
  parser_listen.add_argument(
      '--port', type=int, default=DEFAULT_BIND_PORT,
      help='port to listen, default to %s' % DEFAULT_BIND_PORT)

  parser_rm = subparsers.add_parser('rm', help='removes an existing project')
  parser_rm.add_argument('-n', '--name', required=True,
                         help='name of the project to remove')

  return parser.parse_args()


def main():
  args = _ParseArguments()

  logging_config = DEFAULT_LOGGING_CONFIG
  logging_config['handlers']['file']['filename'] = args.log_file_path
  logging.config.dictConfig(logging_config)

  dkps = DRMKeysProvisioningServer(args.database_file_path, args.gnupg_homedir)
  if args.command == 'init':
    # Convert from command line arguments to a dict.
    gpg_gen_key_args_dict = {}
    for pair in args.gpg_gen_key_args:
      gpg_gen_key_args_dict[pair[0]] = pair[1]
    dkps.Initialize(gpg_gen_key_args_dict, args.server_key_file_path)
  elif args.command == 'destroy':
    message = (
        'This action will remove all projects and keys information and is NOT '
        'recoverable! Are you sure? (y/N)')
    answer = input(textwrap.fill(message, 80) + ' ')
    if answer.lower() != 'y' and answer.lower() != 'yes':
      print('OK, nothing will be removed.')
    else:
      print('Removing all projects and keys information...', end=' ')
      dkps.Destroy()
      print('done.')
  elif args.command == 'listen':
    dkps.ListenForever(args.ip, args.port)
  elif args.command == 'list':
    print(dkps.ListProjects())
  elif args.command == 'add':
    dkps.AddProject(
        args.name, args.uploader_key_file_path, args.requester_key_file_path,
        args.parser_module_file_name, args.filter_module_file_name)
  elif args.command == 'update':
    dkps.UpdateProject(
        args.name, args.uploader_key_file_path, args.requester_key_file_path,
        args.filter_module_file_name)
  elif args.command == 'rm':
    dkps.RemoveProject(args.name)
  else:
    raise ValueError('Unknown command %s' % args.command)


if __name__ == '__main__':
  main()
