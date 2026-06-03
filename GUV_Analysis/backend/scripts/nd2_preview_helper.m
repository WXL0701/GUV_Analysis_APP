function nd2_preview_helper(mode, nd2_path, out_path, series_idx, z_idx, c_idx, t_idx, lut_name, min_value, max_value, bfmatlab_root, c2_idx, lut2_name)
%ND2_PREVIEW_HELPER Bio-Formats backed metadata and preview rendering.
if nargin < 12 || isempty(c2_idx), c2_idx = 1; end
if nargin < 13 || isempty(lut2_name), lut2_name = 'red'; end

if exist(bfmatlab_root, 'dir')
    addpath(genpath(bfmatlab_root));
end

r = bfGetReader(nd2_path);
cleanupObj = onCleanup(@() r.close());

switch lower(char(mode))
    case 'metadata'
        out = localMetadata(r, nd2_path);
        fid = fopen(out_path, 'w');
        if fid < 0
            error('Cannot open metadata output: %s', out_path);
        end
        fprintf(fid, '%s', jsonencode(out));
        fclose(fid);
    case 'preview'
        series_idx = max(0, str2double(char(series_idx)));
        z_idx = max(0, str2double(char(z_idx)));
        c_idx = max(0, str2double(char(c_idx)));
        t_idx = max(0, str2double(char(t_idx)));
        r.setSeries(series_idx);
        plane = bfGetPlaneAtZCT(r, z_idx + 1, c_idx + 1, t_idx + 1);
        img = localRenderPlane(plane, char(lut_name), char(min_value), char(max_value));
        imwrite(img, out_path, 'png');
    case 'preview_merge'
        series_idx = max(0, str2double(char(series_idx)));
        z_idx = max(0, str2double(char(z_idx)));
        c_idx = max(0, str2double(char(c_idx)));
        c2_idx = max(0, str2double(char(c2_idx)));
        t_idx = max(0, str2double(char(t_idx)));
        r.setSeries(series_idx);
        cMax = r.getSizeC() - 1;
        c_idx = min(c_idx, cMax);
        c2_idx = min(c2_idx, cMax);
        plane1 = bfGetPlaneAtZCT(r, z_idx + 1, c_idx + 1, t_idx + 1);
        plane2 = bfGetPlaneAtZCT(r, z_idx + 1, c2_idx + 1, t_idx + 1);
        img = localMergePlanes(plane1, plane2, char(lut_name), char(lut2_name), char(min_value), char(max_value));
        imwrite(img, out_path, 'png');
    otherwise
        error('Unsupported mode: %s', mode);
    end
end

function out = localMetadata(r, nd2_path)
seriesCount = r.getSeriesCount();
series = repmat(struct(), 1, seriesCount);
store = r.getMetadataStore();
for i = 1:seriesCount
    r.setSeries(i - 1);
    pixelSize = [];
    try
        px = store.getPixelsPhysicalSizeX(i - 1);
        if ~isempty(px)
            pixelSize = px.value().doubleValue();
        end
    catch
        pixelSize = [];
    end
    channelCount = r.getSizeC();
    channels = repmat(struct('index', 0, 'name', ''), 1, channelCount);
    for c = 1:channelCount
        chName = sprintf('C%02d', c);
        try
            n = store.getChannelName(i - 1, c - 1);
            if ~isempty(n)
                chName = char(n);
            end
        catch
        end
        channels(c).index = c;
        channels(c).name = chName;
    end
    series(i).index = i - 1;
    series(i).name = sprintf('Series %d', i);
    series(i).size_x = r.getSizeX();
    series(i).size_y = r.getSizeY();
    series(i).size_z = r.getSizeZ();
    series(i).size_c = r.getSizeC();
    series(i).size_t = r.getSizeT();
    series(i).pixel_size_um = pixelSize;
    series(i).channels = channels;
end
[~, filename, ext] = fileparts(nd2_path);
out = struct('filename', [filename ext], 'series', series);
end

function rgb = localRenderPlane(plane, lutName, minValue, maxValue)
plane = double(plane);
if strcmpi(minValue, 'auto') || isempty(minValue)
    lo = prctile(plane(:), 1);
else
    lo = str2double(minValue);
end
if strcmpi(maxValue, 'auto') || isempty(maxValue)
    hi = prctile(plane(:), 99);
else
    hi = str2double(maxValue);
end
if ~isfinite(lo), lo = min(plane(:)); end
if ~isfinite(hi) || hi <= lo, hi = max(plane(:)); end
if hi <= lo, hi = lo + 1; end
gray = max(0, min(1, (plane - lo) ./ (hi - lo)));
switch lower(lutName)
    case 'green'
        rgb = cat(3, zeros(size(gray)), gray, zeros(size(gray)));
    case 'red'
        rgb = cat(3, gray, zeros(size(gray)), zeros(size(gray)));
    case 'magenta'
        rgb = cat(3, gray, zeros(size(gray)), gray);
    case 'cyan'
        rgb = cat(3, zeros(size(gray)), gray, gray);
    otherwise
        rgb = repmat(gray, [1 1 3]);
end
rgb = im2uint8(rgb);
end

function rgb = localMergePlanes(plane1, plane2, lut1, lut2, minValue, maxValue)
rgb1 = im2double(localRenderPlane(plane1, lut1, minValue, maxValue));
rgb2 = im2double(localRenderPlane(plane2, lut2, minValue, maxValue));
rgb = im2uint8(min(1, rgb1 + rgb2));
end
