# MATLAB Runtime Guide

## Overview
This deployment uses a single MATLAB runtime: `R2024a`. The system no longer switches between multiple MATLAB versions.

## Features

### 1. MATLAB Runtime
In the **System Config > MATLAB Environment** section, the runtime is fixed to `MATLAB R2024a`.

- **Behavior**:
  - The application always uses `/usr/local/MATLAB/R2024a/bin/matlab`.
  - `system.matlab_version` is kept as `R2024a` for compatibility with existing configuration storage.

### 2. Enhanced Path Display
The display logic for the **Package Version** (Pipeline Root) has been updated to ensure the full path is visible.
- Long paths are now wrapped and displayed in a dedicated box with monospace font for better readability.
- Example: `\home\guv_Analysis\GUV_Analysis_APP\GUV_Analysis_V1.1.2`

## Compatibility
- Existing migrated configuration values remain readable.
- Task execution is pinned to `R2024a` even if an older version value is found in configuration.

## Troubleshooting
- If tasks fail to start, ensure that `R2024a` is correctly installed at `/usr/local/MATLAB/R2024a/bin/matlab`.
- Check the `runtime.log` of the task to verify that `R2024a` is being used.
