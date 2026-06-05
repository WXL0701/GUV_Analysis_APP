function TTracks = guvSeries_trackFromMats(Paths, Cfg, Thr, frameGetter)
%GUVSERIES_TRACKFROMMATS 读取 FramesMAT 并运行 guvTrack_trackCentroids。
files = guvUtil_sortFrameFiles(dir(fullfile(Paths.OutFrames, 'Time_*_Data.mat')));
files = localApplyTrackFrameRange(files, Cfg);

trackOpts = Cfg.Track.Opts;
trackOpts.StoreImg = false;
trackOpts.SaveDiag = true;
trackOpts.DiagOutDir = fullfile(Paths.OutSeries, 'TrackDiag');
trackOpts.DiagTag = sprintf('%s_%s', Paths.SeriesName, Paths.CName);
if ~isempty(frameGetter)
    trackOpts.FrameGetter = frameGetter;
end

TTracks = guvTrack_trackCentroids(files, Thr.trackGate_px, Cfg.Track.MinLen, Cfg.Track.MaxGap, trackOpts);


% 保存
if Cfg.Output.SaveTracksMAT
    outMat = fullfile(Paths.OutSeries, 'TTracks.mat');
    s = whos('TTracks');
    if s.bytes > 2^31-1
        save(outMat, 'TTracks', 'Cfg', '-v7.3');
    else
        save(outMat, 'TTracks', 'Cfg', '-v7');
    end
end

function filesOut = localApplyTrackFrameRange(filesIn, Cfg)
filesOut = filesIn;
if isempty(filesIn) || ~isfield(Cfg, 'Track')
    return;
end

startFrame = [];
endFrame = [];
if isfield(Cfg.Track, 'FrameRange') && ~isempty(Cfg.Track.FrameRange) && numel(Cfg.Track.FrameRange) >= 2
    startFrame = localFirstNumber(Cfg.Track.FrameRange(1));
    endFrame = localFirstNumber(Cfg.Track.FrameRange(2));
else
    if isfield(Cfg.Track, 'StartFrame') && ~isempty(Cfg.Track.StartFrame)
        startFrame = localFirstNumber(Cfg.Track.StartFrame);
    end
    if isfield(Cfg.Track, 'EndFrame') && ~isempty(Cfg.Track.EndFrame)
        endFrame = localFirstNumber(Cfg.Track.EndFrame);
    end
end

if isempty(startFrame) && isempty(endFrame)
    return;
end
if isempty(startFrame), startFrame = -inf; end
if isempty(endFrame), endFrame = inf; end
startFrame = floor(double(startFrame));
endFrame = floor(double(endFrame));
if startFrame < 1
    error('Track.StartFrame must be >= 1.');
end
if endFrame < startFrame
    error('Track.EndFrame must be >= Track.StartFrame.');
end

keep = false(size(filesIn));
for i = 1:numel(filesIn)
    frameNo = localFrameNumber(filesIn(i).name);
    keep(i) = frameNo >= startFrame && frameNo <= endFrame;
end
filesOut = filesIn(keep);
if isempty(filesOut)
    error('Track frame range [%d, %d] produced no Time_*_Data.mat files.', startFrame, endFrame);
end
end

function v = localFirstNumber(x)
if isempty(x)
    v = [];
    return;
end
if isnumeric(x)
    v = x(1);
    return;
end
v = str2double(char(x));
if isnan(v)
    v = [];
end
end

function n = localFrameNumber(name)
tok = regexp(name, 'Time_(\d+)_Data\.mat', 'tokens', 'once');
if isempty(tok)
    error('Unable to parse frame number from %s.', name);
end
n = str2double(tok{1});
end
end
