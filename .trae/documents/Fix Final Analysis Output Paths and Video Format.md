I will implement the changes to ensure the final CSV and Video files are correctly placed in the `output/final` directory and are downloadable from the frontend.

### 1. Backend & MATLAB: Correct File Output Locations

* **Modify** **`guvCompute_collectAllXYResults.m`**:

  * Change the output path of `AllXYResults.csv` to `fullfile(OutRoot, 'output', 'final', 'AllXYResults.csv')`.

  * Ensure the `output/final` directory is created if it doesn't exist.

* **Modify** **`guvVideo_exportSeries.m`** **(Final Video Export)**:

  * Change the default video format from `'mp4'` to `'avi'` (Motion JPEG AVI) for Linux compatibility.

  * Change the output directory logic to place videos in `.../output/final` instead of the subfolder `XY.../Video`.

  * Ensure the filename includes the Series ID (e.g., `XY001_C1.avi`) to prevent conflicts in the unified folder.

  * 检查更改为avi格式后final视频的输出matlab代码是否有效。

* **Update** **`run_matlab_task.m`** **(Backend Wrapper)**:

  * Disable the redundant "legacy" CSV copy logic, as MATLAB will now output the file directly to the correct location.

  * (Debug mode logic will remain unchanged as requested).

### 2. Backend API: Update Download Paths

* **Modify** **`app/api/routes/tasks.py`**:

  * Update the `download_results_csv` endpoint to prioritize looking for `AllXYResults.csv` in `output/final/`.

### 3. Frontend: Add Video Download Support

* **Modify** **`TaskParams.vue`**:

  * Update `fetchArtifacts` logic to allow fetching artifacts in "Final" mode (currently restricted to Debug mode).

  * Add a new section in the "Run Status" card to list downloadable AVI video files when in Final mode.

  * Ensure the "Download CSV" button works with the new file location.

