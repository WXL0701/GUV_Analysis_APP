export interface ParamSchema {
    key: string;
    label: string;
    type: 'number' | 'text' | 'boolean' | 'select' | 'array_number' | 'array_select' | 'array_string' | 'slider';
    tooltip: string;
    default?: any;
    min?: number;
    max?: number;
    step?: number;
    options?: string[]; // For select
    allowEmpty?: boolean; // For arrays that can be empty
}

export interface ParamGroup {
    label: string;
    key: string; // Top level key in config, e.g., 'Read'
    params: ParamSchema[];
}

export const paramGroups: ParamGroup[] = [
    {
        label: 'Read Settings (Input)',
        key: 'Read',
        params: [
            { 
                key: 'SelectXYs', 
                label: 'Select XYs', 
                type: 'array_number', 
                tooltip: 'Select specific XY positions to process (e.g. [1, 5, 10]). Leave empty to process all.', 
                default: [] 
            },
            { 
                key: 'Z', 
                label: 'Z Plane', 
                type: 'number', 
                tooltip: 'Z-plane index to process (Default: 1)', 
                default: 1 
            },
            { 
                key: 'CList', 
                label: 'Channel Indices', 
                type: 'array_number', 
                tooltip: 'List of channel indices to read (e.g. [1, 2])', 
                default: [1, 2] 
            },
            { 
                key: 'CNames', 
                label: 'Channel Names', 
                type: 'array_string', 
                tooltip: 'Names for channels (e.g. ["488", "640"]), used for output files and columns.', 
                default: ['488', '640'] 
            },
            { 
                key: 'CType', 
                label: 'Channel Types', 
                type: 'array_select', 
                options: ['inner', 'mem'], 
                tooltip: "Defines how to construct the mask for each channel:\n'inner': Solid area\n'mem': Fixed thickness band around boundary", 
                default: ['inner', 'inner'] 
            },
            { 
                key: 'RefC', 
                label: 'Reference Channel', 
                type: 'number', 
                tooltip: 'Main channel index used for alignment and organization.', 
                default: 1 
            }
        ]
    },
    {
        label: 'Fusion (Multi-Channel)',
        key: 'Fuse',
        params: [
            { 
                key: 'Pair.MaxDist_um', 
                label: 'Max Pair Dist (um)', 
                type: 'number', 
                step: 0.5,
                tooltip: 'Maximum distance between centroids to consider them the same object (typically 3-10 um).', 
                default: 3 
            },
            { 
                key: 'Pair.UseIoU', 
                label: 'Use IoU Check', 
                type: 'boolean', 
                tooltip: 'Enable Intersection over Union (IoU) check for secondary confirmation.', 
                default: true 
            },
            { 
                key: 'Pair.MinIoU', 
                label: 'Min IoU', 
                type: 'number', 
                step: 0.01,
                tooltip: 'Minimum IoU threshold if IoU check is enabled.', 
                default: 0.05 
            }
        ]
    },
    {
        label: 'Detection',
        key: 'Detect',
        params: [
            { 
                key: 'MinMajor_um', 
                label: 'Min Major Axis (um)', 
                type: 'number', 
                tooltip: 'Minimum major axis length for an object to be detected.', 
                default: 5 
            },
            { 
                key: 'MaxMajor_um', 
                label: 'Max Major Axis (um)', 
                type: 'number', 
                tooltip: 'Maximum major axis length for an object to be detected.', 
                default: 80 
            },
            { 
                key: 'SuppressCloseOnMem', 
                label: 'Suppress Close Mem', 
                type: 'boolean', 
                tooltip: 'Suppress nearby detections on membrane channels (equivalent to old logic).', 
                default: true 
            },
            { 
                key: 'Opts.bin.sigma', 
                label: 'Sigma (Smooth)', 
                type: 'number', 
                step: 0.1,
                tooltip: 'Gaussian smoothing sigma (px).', 
                default: 1.2 
            },
            { 
                key: 'Opts.bin.adapt_sensitivity', 
                label: 'Sensitivity', 
                type: 'slider', 
                min: 0, 
                max: 1, 
                step: 0.01,
                tooltip: 'Adaptive threshold sensitivity (0-1). Higher values detect more foreground.', 
                default: 0.15 
            },
            { 
                key: 'Opts.bin.minHoleArea', 
                label: 'Min Hole Area (px)', 
                type: 'number', 
                tooltip: 'Minimum area of holes to fill inside objects.', 
                default: 10 
            },
             { 
                key: 'Opts.inner.areaOpen', 
                label: 'Min Area Open (px)', 
                type: 'number', 
                tooltip: 'Remove small objects smaller than this area.', 
                default: 150 
            },
            { 
                key: 'Opts.band.width_px', 
                label: 'Mem Band Width (px)', 
                type: 'number', 
                tooltip: 'Thickness of the membrane ring for intensity measurement.', 
                default: 5 
            }
        ]
    },
    {
        label: 'Post-Processing (Watershed)',
        key: 'Post',
        params: [
            { 
                key: 'Watershed.Enable', 
                label: 'Enable Watershed', 
                type: 'boolean', 
                tooltip: 'Enable area coverage based adaptive watershed segmentation.', 
                default: true 
            },
            { 
                key: 'Watershed.Tau', 
                label: 'Tau (Coverage)', 
                type: 'slider', 
                min: 0, 
                max: 1, 
                step: 0.05,
                tooltip: 'Area coverage threshold. Smaller values trigger more aggressive splitting.', 
                default: 0.60 
            },
            { 
                key: 'Watershed.hLow', 
                label: 'H-Minima Low', 
                type: 'number', 
                step: 0.1,
                tooltip: 'H-minima threshold for easy splitting.', 
                default: 2.0 
            },
             { 
                key: 'Watershed.hHigh', 
                label: 'H-Minima High', 
                type: 'number', 
                step: 0.1,
                tooltip: 'H-minima threshold for conservative splitting.', 
                default: 10.0 
            }
        ]
    },
    {
        label: 'Tracking',
        key: 'Track',
        params: [
            { 
                key: 'DistGate_um', 
                label: 'Max Track Dist (um)', 
                type: 'number', 
                tooltip: 'Maximum distance an object can move between frames.', 
                default: 8 
            },
            { 
                key: 'MaxGap', 
                label: 'Max Gap (Frames)', 
                type: 'number', 
                tooltip: 'Maximum number of missing frames allowed in a track.', 
                default: 2 
            },
            { 
                key: 'MinLen', 
                label: 'Min Length (Frames)', 
                type: 'number', 
                tooltip: 'Minimum length of a valid track.', 
                default: 10 
            },
             { 
                key: 'Opts.EstimateGlobalDrift', 
                label: 'Estimate Drift', 
                type: 'boolean', 
                tooltip: 'Enable global drift estimation and correction.', 
                default: true 
            }
        ]
    },
    {
        label: 'Output & Debug',
        key: 'Output',
        params: [
            { 
                key: 'SaveFrameStore', 
                label: 'Save FrameStore', 
                type: 'boolean', 
                tooltip: 'Save HDF5 FrameStore for video background and fast access.', 
                default: true 
            },
             { 
                key: 'FrameStoreMode', 
                label: 'FrameStore Mode', 
                type: 'select', 
                options: ['ref', 'multi'],
                tooltip: "'ref': Save only reference channel (smallest).\n'multi': Save all channels (for merge video).", 
                default: 'ref' 
            }
        ]
    },
     {
        label: 'Debug Options',
        key: 'Debug',
        params: [
            { 
                key: 'Enable', 
                label: 'Enable Debug Output', 
                type: 'boolean', 
                tooltip: 'Master switch for debug outputs.', 
                default: false 
            },
            { 
                key: 'SingleXYOnly', 
                label: 'Single XY Only', 
                type: 'boolean', 
                tooltip: 'Only process one XY position (the first one selected) for debugging.', 
                default: false 
            },
            { 
                key: 'SaveVideo', 
                label: 'Save Debug Video', 
                type: 'boolean', 
                tooltip: 'Generate debug video with overlays.', 
                default: true 
            },
            { 
                key: 'VideoFPS', 
                label: 'Video FPS', 
                type: 'number', 
                tooltip: 'Frames per second for debug video.', 
                default: 10 
            }
        ]
    },
    {
        label: 'Parallel Processing',
        key: 'Parallel',
        params: [
            { 
                key: 'Enable', 
                label: 'Enable Parallel', 
                type: 'boolean', 
                tooltip: 'Enable parallel processing (parfor).', 
                default: true 
            },
            { 
                key: 'PoolSize', 
                label: 'Pool Size', 
                type: 'array_number', 
                tooltip: 'Manual limit for parallel pool workers. Empty/<=0 for max available. Example: [6] to save memory.', 
                default: [3] 
            }
        ]
    },
    {
        label: 'Compute Settings',
        key: 'Compute',
        params: [
            {
                key: 'Enable',
                label: 'Enable Compute',
                type: 'boolean',
                tooltip: 'Enable post-tracking computation (e.g. intensity analysis).',
                default: true
            },
            {
                key: 'n_keep',
                label: 'Fourier Coeffs',
                type: 'number',
                tooltip: 'Number of low-frequency coefficients to keep for Fourier smoothing. Smaller = smoother, Larger = closer to original contour.',
                default: 12
            },
            {
                key: 'ExportCSV',
                label: 'Export CSV',
                type: 'boolean',
                tooltip: 'Export computed metrics to CSV files.',
                default: true
            }
        ]
    },
    {
        label: 'Video Generation',
        key: 'Video',
        params: [
            {
                key: 'Enable',
                label: 'Enable Video',
                type: 'boolean',
                tooltip: 'Enable final video generation (Merge/Contrast adjusted).',
                default: false
            },
            {
                key: 'Format',
                label: 'Format',
                type: 'select',
                options: ['mp4', 'avi'],
                tooltip: 'Video output format.',
                default: 'mp4'
            },
            {
                key: 'FPS',
                label: 'FPS',
                type: 'number',
                tooltip: 'Frames per second for final video.',
                default: 10
            },
            {
                key: 'UseFrameStoreOnly',
                label: 'Use FrameStore Only',
                type: 'boolean',
                tooltip: 'Generate video using only the fast FrameStore cache.',
                default: false
            }
        ]
    }
];
