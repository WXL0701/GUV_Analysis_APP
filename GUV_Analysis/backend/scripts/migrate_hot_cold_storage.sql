ALTER TABLE IF EXISTS tasks
  ADD COLUMN IF NOT EXISTS nd2_local_path text,
  ADD COLUMN IF NOT EXISTS nd2_local_bytes bigint,
  ADD COLUMN IF NOT EXISTS nd2_local_saved_at timestamp,
  ADD COLUMN IF NOT EXISTS nd2_local_deleted_at timestamp;

ALTER TABLE IF EXISTS task_runs
  ADD COLUMN IF NOT EXISTS run_dir_archive text,
  ADD COLUMN IF NOT EXISTS archived_at timestamp;
