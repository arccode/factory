CREATE TABLE IF NOT EXISTS settings (
    key TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
    );

CREATE TABLE IF NOT EXISTS projects (
    name TEXT NOT NULL PRIMARY KEY,
    uploader_key_fingerprint TEXT NOT NULL,
    requester_key_fingerprint TEXT NOT NULL,
    parser_module_file_name TEXT NOT NULL,
    filter_module_file_name TEXT NULL,
    UNIQUE(uploader_key_fingerprint),
    UNIQUE(requester_key_fingerprint)
    );

CREATE TABLE IF NOT EXISTS drm_keys (
    id INTEGER NOT NULL PRIMARY KEY,
    project_name TEXT NOT NULL,
    drm_key_hash TEXT NOT NULL,
    encrypted_drm_key TEXT NOT NULL,
    device_serial_number TEXT NULL,
    FOREIGN KEY(project_name) REFERENCES projects(name),
    UNIQUE(project_name, drm_key_hash),
    UNIQUE(project_name, encrypted_drm_key),
    UNIQUE(project_name, device_serial_number)
    );

CREATE INDEX IF NOT EXISTS pu ON projects (uploader_key_fingerprint);
CREATE INDEX IF NOT EXISTS pr ON projects (requester_key_fingerprint);
CREATE INDEX IF NOT EXISTS kpd ON drm_keys (project_name, device_serial_number);
