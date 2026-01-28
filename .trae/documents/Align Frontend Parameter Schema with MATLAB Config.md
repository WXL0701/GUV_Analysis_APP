Based on the comparison between `taskParamsSchema.ts` (Frontend) and `guvPipeline_configDefault.m` (MATLAB backend), I have identified discrepancies in the tooltip descriptions and parameter availability, specifically regarding the `n_keep` parameter for Fourier smoothing.

The user pointed out that `n_keep` in the frontend (labeled "Keep Tracks") has an incorrect tooltip description compared to the MATLAB config ("傅里叶平滑：保留的低频系数个数...").

Here is the plan to align the frontend schema with the MATLAB backend configuration:

## 1. Correct `n_keep` Parameter
- **File**: `frontend/src/config/taskParamsSchema.ts`
- **Action**: Update the label and tooltip for `Compute.n_keep`.
  - **Old Label**: "Keep Tracks"
  - **New Label**: "Fourier Coeffs" (or "Fourier Keep N")
  - **Old Tooltip**: "Number of longest tracks to keep for plotting/analysis."
  - **New Tooltip**: "Number of low-frequency coefficients to keep for Fourier smoothing (smaller = smoother, larger = closer to original contour)."

## 2. Review and Align Other Parameters
I will perform a pass on other parameters to ensure their tooltips match the semantic meaning in `guvPipeline_configDefault.m`:

- **Parallel.PoolSize**: Confirm tooltip mentions manual limit for memory control.
- **Video.Quality**: Add tooltip "Quality for mp4/avi (0-100)".
- **Video.Contrast**: Add tooltip explaining `[]` means auto-estimation.

## 3. Rebuild Frontend
- Rebuild the frontend container to apply the schema changes.

This will ensure the user interface accurately reflects the underlying algorithm's parameters as documented in the MATLAB code.
