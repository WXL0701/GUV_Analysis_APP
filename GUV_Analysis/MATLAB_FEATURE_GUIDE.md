# MATLAB Version Selection Feature Guide

## Overview
We have introduced a new feature in the System Configuration interface to allow users to select between different MATLAB versions. This ensures that the analysis pipeline runs with the appropriate MATLAB runtime environment.

## Features

### 1. MATLAB Version Selection
In the **System Config > MATLAB Environment** section, you will now find a **MATLAB Version** dropdown menu.

- **Options**:
  - **MATLAB R2018a**: Uses the runtime at `/usr/local/MATLAB/R2018a`.
  - **MATLAB R2024a**: Uses the runtime at `/usr/local/MATLAB/R2024a`.
  
- **Behavior**:
  - Selecting a version and changing it saves the preference to the system configuration (`system.matlab_version`).
  - This setting is persistent and will be used for all future analysis tasks.
  - The backend worker automatically switches between `matlab2018a` and `matlab2024a` commands based on your selection.

### 2. Enhanced Path Display
The display logic for the **Package Version** (Pipeline Root) has been updated to ensure the full path is visible.
- Long paths are now wrapped and displayed in a dedicated box with monospace font for better readability.
- Example: `\home\guv_Analysis\GUV_Analysis_APP\GUV_Analysis_V1.1.2`

## Compatibility
- **Backward Compatibility**: If no version is selected (e.g., after a fresh install), the system defaults to **R2018a** logic (using `matlab` or `matlab2018a` command).
- **Task Execution**: The selected version is applied dynamically at runtime. You can switch versions between tasks without restarting the server.

## Troubleshooting
- If tasks fail to start, ensure that the selected MATLAB version is correctly installed on the server at the specified path.
- Check the `runtime.log` of the task to verify which MATLAB binary was used (e.g., `Configuration loaded: system.matlab_version=R2024a -> BIN=matlab2024a`).
