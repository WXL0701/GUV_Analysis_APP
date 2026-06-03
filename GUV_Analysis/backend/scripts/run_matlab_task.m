function run_matlab_task(mode, nd2_path, params_path, out_dir, pipeline_root)
    % RUN_MATLAB_TASK Wrapper for GUV_Pipeline
    % Integrates the GUV_Analysis_V1.1.2 package with the backend.
    
    fprintf("Wrapper: Starting Task...\n");
    fprintf("Wrapper: Mode=%s\n", mode);
    fprintf("Wrapper: ND2=%s\n", nd2_path);
    fprintf("Wrapper: Params=%s\n", params_path);
    fprintf("Wrapper: OutDir=%s\n", out_dir);
    fprintf("Wrapper: PipelineRoot=%s\n", pipeline_root);

    % 1. Add Pipeline to Path
    if ~exist(pipeline_root, 'dir')
        error("Pipeline root not found: %s", pipeline_root);
    end
    addpath(genpath(pipeline_root));

    % 2. Prepare Config
    % Read JSON params from backend
    if exist(params_path, 'file')
        txt = fileread(params_path);
        user_params = jsondecode(txt);
    else
        fprintf("Wrapper: Warning - Params file missing, using empty struct.\n");
        user_params = struct();
    end

    % Enforce paths
    user_params.ND2Path = nd2_path;
    user_params.OutRoot = out_dir;

    % Mode-specific overrides
    if ~isfield(user_params, 'Debug'), user_params.Debug = struct(); end
    
    if strcmp(mode, 'debug')
        fprintf("Wrapper: Configuring for DEBUG mode.\n");
        user_params.Debug.Enable = true;
        % Optional: Force single XY for faster debug?
        % user_params.Read.SelectXYs = [1]; 
    else
        fprintf("Wrapper: Configuring for FINAL mode.\n");
        user_params.Debug.Enable = false;
    end

    % 3. Run Pipeline
    fprintf("Wrapper: Calling GUV_Pipeline...\n");
    try
        % Capture output? MATLAB -batch sends to stdout anyway.
        GUV_Pipeline(nd2_path, out_dir, user_params);
        fprintf("Wrapper: GUV_Pipeline completed successfully.\n");
    catch ME
        fprintf("Wrapper: Error in GUV_Pipeline:\n%s\n", ME.message);
        % Dump stack
        for k = 1:length(ME.stack)
            fprintf('  In %s (line %d)\n', ME.stack(k).name, ME.stack(k).line);
        end
        % Re-throw to signal failure to worker
        error(ME.message);
    end

    if strcmp(mode, 'debug')
        avis = dir(fullfile(out_dir, '**', 'DebugVideo', '*.avi'));
        for i = 1:length(avis)
            src = fullfile(avis(i).folder, avis(i).name);
            [p, n] = fileparts(src);
            dest = fullfile(p, [n '.mp4']);
            if exist(dest, 'file')
                continue;
            end
            cmd = localFfmpegCommand(src, dest);
            [status, out] = system(cmd);
            if status == 0 && exist(dest, 'file')
                try
                    delete(src);
                catch
                end
                fprintf("Wrapper: Transcoded debug video to %s\n", dest);
            else
                fprintf("Wrapper: Warning - ffmpeg transcode failed for %s\n%s\n", src, out);
            end
        end
    end

    % 4. Standardize Artifacts for Backend
    % The backend expects:
    %   Debug -> out_dir/output/debug/preview.mp4
    %   Final -> out_dir/output/final/result.csv
    
    % Create standard dirs if missing
    std_debug_dir = fullfile(out_dir, 'output', 'debug');
    std_final_dir = fullfile(out_dir, 'output', 'final');
    if ~exist(std_debug_dir, 'dir'), mkdir(std_debug_dir); end
    if ~exist(std_final_dir, 'dir'), mkdir(std_final_dir); end

    % A) Handle Video
    if strcmp(mode, 'debug')
        mp4s = dir(fullfile(out_dir, '**', '*.mp4'));
        avis = dir(fullfile(out_dir, '**', '*.avi'));
        if ~isempty(mp4s)
            src = fullfile(mp4s(1).folder, mp4s(1).name);
            dest = fullfile(std_debug_dir, 'preview.mp4');
            copyfile(src, dest);
            fprintf("Wrapper: Copied preview video to %s\n", dest);
        elseif ~isempty(avis)
            src = fullfile(avis(1).folder, avis(1).name);
            % Try to force transcode AVI to MP4 for preview
            dest_mp4 = fullfile(std_debug_dir, 'preview.mp4');
            cmd = localFfmpegCommand(src, dest_mp4);
            [status, ~] = system(cmd);
            
            if status == 0 && exist(dest_mp4, 'file')
                fprintf("Wrapper: Transcoded fallback AVI to %s\n", dest_mp4);
            else
                % Fallback to AVI copy
                dest = fullfile(std_debug_dir, 'preview.avi');
                copyfile(src, dest);
                fprintf("Wrapper: Copied preview video to %s (Transcode failed)\n", dest);
            end
        else
            fprintf("Wrapper: Warning - No preview video generated in debug mode.\n");
        end
    end

    % B) Handle CSV
    % MATLAB now outputs AllXYResults.csv to output/final directly.
    final_csv = fullfile(std_final_dir, 'AllXYResults.csv');
    if exist(final_csv, 'file')
        fprintf("Wrapper: Found result CSV at %s\n", final_csv);
    else
        fprintf("Wrapper: Warning - AllXYResults.csv not found in %s\n", std_final_dir);
    end

    fprintf("Wrapper: Task Done.\n");
end

function cmd = localFfmpegCommand(src, dest)
    ffmpeg_bin = getenv('FFMPEG_BIN');
    if isempty(ffmpeg_bin)
        ffmpeg_bin = '/usr/bin/ffmpeg';
    end
    cmd = sprintf('env -u LD_LIBRARY_PATH -u LD_PRELOAD \"%s\" -y -loglevel error -i \"%s\" -pix_fmt yuv420p \"%s\"', ...
        ffmpeg_bin, src, dest);
end
