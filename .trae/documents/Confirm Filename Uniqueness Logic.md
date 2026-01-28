I will fix the duplicate artifacts issue in the backend `list_run_artifacts` function.

### 1. Backend: Fix Duplicate Artifact Listing

* **Modify** **`app/api/routes/tasks.py`**:
  * Update the `list_run_artifacts` function.
  * Introduce a `seen_paths` set to track processed files.
  * Before adding a file to `videos` or `csvs`, check if its absolute path is already in `seen_paths`.
  * If not seen, add the absolute path to `seen_paths` and proceed with adding the file to the response list.
  * This will prevent the same file from being added multiple times when `os.walk` traverses overlapping directories (e.g., `run_dir` which contains `debug_dir` and `final_dir`).

### 2. Verification

* **Verify**:
  * Restart the backend service.
  * Check the frontend to ensure that the artifact list no longer contains duplicates.
