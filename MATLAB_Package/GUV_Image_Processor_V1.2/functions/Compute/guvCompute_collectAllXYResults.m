function AllXYResults = guvCompute_collectAllXYResults(OutRoot, SeriesPrefix, CNames)
%GUVCOMPUTE_COLLECTALLXYRESULTS 汇总所有 XY 的 AllResults.csv 为一个总表
% =========================================================================
% 目标：根据每个 XY 子目录下的
%   XY###/Computation/AllResults.csv
% 汇总生成 OutputPath 根目录的 AllXYResults.csv（用于替代 GUV_MASTER_DB.csv 的“总表”作用）。
%
% 输入：
%   OutRoot      : Pipeline 输出根目录（OutputPath）
%   SeriesPrefix : 子目录前缀（默认 'XY'）
%
% 额外：
%   - 输出会新增 GlobalID 列：对每个 (SeriesName, TrackID) 生成全局唯一ID，
%     便于跨 XY 统计/过滤。
%
% 输出：
%   AllXYResults : 汇总后的 table（若没有找到任何 AllResults.csv，则为空表）

    if nargin < 1 || isempty(OutRoot)
        error('OutRoot 为空。');
    end
    if nargin < 2 || isempty(SeriesPrefix)
        SeriesPrefix = 'XY';
    end

    if nargin < 3
        CNames = [];
    end
    if isempty(CNames)
        CNames = localTryLoadCNames(OutRoot);
    end


    patt = fullfile(OutRoot, sprintf('%s*', SeriesPrefix), 'Computation', 'AllResults.csv');
    files = dir(patt);

    if isempty(files)
        AllXYResults = table();
        return;
    end

    % ------- 按 XY 序号排序，保证 GlobalID 的叠加顺序稳定 -------
    seriesNum = nan(numel(files),1);
    for i = 1:numel(files)
        % e.g. .../XY001/Computation/AllResults.csv
        p = files(i).folder;
        [~, xyName] = fileparts(fileparts(p)); % 上两级得到 XY###
        tok = regexp(xyName, sprintf('^%s(\\d+)$', SeriesPrefix), 'tokens', 'once');
        if ~isempty(tok)
            seriesNum(i) = str2double(tok{1});
        end
    end
    [~, ord] = sort(seriesNum);
    files = files(ord);

    % 写到 OutRoot/output/final
    outFinalDir = fullfile(OutRoot, 'output', 'final');
    if ~exist(outFinalDir, 'dir')
        mkdir(outFinalDir);
    end
    outCsv = fullfile(outFinalDir, 'AllXYResults.csv');

    [ok, hdrVars, hdrVarsValid] = localStreamCollectAllResults(files, outCsv, SeriesPrefix, CNames);
    if ok
        if isempty(hdrVarsValid)
            AllXYResults = table();
        else
            AllXYResults = cell2table(cell(0, numel(hdrVarsValid)), 'VariableNames', hdrVarsValid);
        end
        if ~isempty(hdrVars)
            try
                AllXYResults.Properties.VariableDescriptions = hdrVars;
            catch
            end
        end
    else
        AllXYResults = table();
        warning('guvCompute:NoResults', 'No valid results collected. AllXYResults is empty.');
    end
end

function T = localReadAllResultsCSV(fp)
fid = fopen(fp, 'r');
if fid < 0
    error('Cannot open file: %s', fp);
end
cleaner = onCleanup(@() fclose(fid));

hdr = fgetl(fid);
if ~ischar(hdr) || isempty(strtrim(hdr))
    T = table();
    return;
end

vars = strsplit(hdr, ',');
vars = cellfun(@strtrim, vars, 'UniformOutput', false);
if ~isempty(vars)
    if ~isempty(vars{1}) && vars{1}(1) == char(65279)
        vars{1} = vars{1}(2:end);
    end
end

for k = 1:numel(vars)
    if ~isvarname(vars{k})
        vars{k} = matlab.lang.makeValidName(vars{k});
    end
end
vars = matlab.lang.makeUniqueStrings(vars, {}, namelengthmax);

if numel(vars) < 2
    T = table();
    return;
end

fmt = ['%s' repmat('%f', 1, numel(vars) - 1)];
C = textscan(fid, fmt, 'Delimiter', ',', 'EmptyValue', NaN, 'ReturnOnError', false);

if isempty(C) || isempty(C{1})
    T = table();
    return;
end

T = table(string(C{1}), 'VariableNames', {vars{1}});
for k = 2:numel(vars)
    v = C{k};
    if iscell(v)
        v = string(v);
    end
    T.(vars{k}) = v;
end
end

function [ok, headerVars, headerVarsValid] = localStreamCollectAllResults(files, outCsv, SeriesPrefix, CNames)
ok = false;
headerVars = {};
headerVarsValid = {};


fidw = fopen(outCsv, 'w');
if fidw < 0
    return;
end
cleanw = onCleanup(@() fclose(fidw));

offset = 0;
headerWritten = false;
trackIdx = 0;
seriesIdx = 0;
expectCols = 0;

for i = 1:numel(files)
    fp = fullfile(files(i).folder, files(i).name);
    if files(i).bytes == 0
        continue;
    end

    fid = fopen(fp, 'r');
    if fid < 0
        continue;
    end
    cleanr = onCleanup(@() fclose(fid));

    hdr = fgetl(fid);
    if ~ischar(hdr) || isempty(strtrim(hdr))
        continue;
    end

    vars = strsplit(hdr, ',');
    vars = cellfun(@strtrim, vars, 'UniformOutput', false);
    if ~isempty(vars) && ~isempty(vars{1}) && vars{1}(1) == char(65279)
        vars{1} = vars{1}(2:end);
    end

    if ~headerWritten
        headerVarsRaw = [vars, {'GlobalID'}];
        headerVars = localMakeChannelHeader(headerVarsRaw, CNames);

        headerVarsValid = cell(size(headerVarsRaw));
        for k = 1:numel(headerVarsRaw)
            v = headerVarsRaw{k};
            if ~isvarname(v)
                v = matlab.lang.makeValidName(v);
            end
            headerVarsValid{k} = v;
        end
        headerVarsValid = matlab.lang.makeUniqueStrings(headerVarsValid, {}, namelengthmax);

        trackIdx = find(strcmp(vars, 'TrackID'), 1, 'first');
        seriesIdx = find(strcmp(vars, 'SeriesName'), 1, 'first');
        if isempty(trackIdx)
            return;
        end
        expectCols = numel(vars);

        fprintf(fidw, '%s\n', strjoin(headerVars, ','));
        headerWritten = true;
    else
        if expectCols ~= numel(vars)
            continue;
        end
    end

    [~, xyName] = fileparts(fileparts(files(i).folder));

    maxTid = 0;
    hasMax = false;

    while true
        line = fgetl(fid);
        if ~ischar(line)
            break;
        end
        if isempty(line)
            continue;
        end
        parts = strsplit(line, ',');
        if numel(parts) ~= expectCols
            continue;
        end
        tid = str2double(strtrim(parts{trackIdx}));
        if isnan(tid)
            continue;
        end
        if seriesIdx > 0 && isempty(strtrim(parts{seriesIdx}))
            parts{seriesIdx} = xyName;
        end
        gid = tid + offset;
        if ~hasMax || tid > maxTid
            maxTid = tid;
            hasMax = true;
        end
        fprintf(fidw, '%s,%g\n', strjoin(parts, ','), gid);
    end

    if hasMax
        offset = offset + maxTid;
    end

    clear cleanr
end

ok = headerWritten;
end

% -------------------- local helpers（channel header & csv header rewrite） --------------------
function hdr = localMakeChannelHeader(vars, CNames)
%localMakeChannelHeader 把变量名里的 _C01/_C02... 替换为 CNames 前缀。
% 例：meanIntensities_bg_C01 -> 488_meanIntensities_bg
hdr = vars;
if isempty(vars) || isempty(CNames)
    return;
end
if isstring(CNames)
    CNames = cellstr(CNames);
end
if ischar(CNames)
    CNames = cellstr(CNames);
end

for ci = 1:numel(CNames)
    cname = CNames{ci};
    if isempty(cname), continue; end
    cname = regexprep(cname, '\s+', '');
    cname = strrep(cname, ',', '_');

    suf = sprintf('_C%02d', ci);
    for k = 1:numel(vars)
        v = vars{k};
        if endsWith(v, suf)
            base = regexprep(v, [suf '$'], '');
            hdr{k} = sprintf('%s_%s', cname, base);
        end
    end
end
end

function localRewriteCsvHeader(fp, header)
%localRewriteCsvHeader 用自定义 header 覆盖 CSV 第一行（不改数据行）
if isempty(header) || ~isfile(fp)
    return;
end

fid = -1;
fidw = -1;
try
    fid = fopen(fp, 'r');
    if fid < 0
        return;
    end
    fgetl(fid); % 丢弃原始第一行
    rest = fread(fid, '*char')';
    fclose(fid);
    fid = -1;

    fidw = fopen(fp, 'w');
    if fidw < 0
        return;
    end
    fprintf(fidw, '%s\n', strjoin(header, ','));
    fwrite(fidw, rest, 'char');
    fclose(fidw);
    fidw = -1;

catch
    if fid > 0
        try, fclose(fid); catch, end
    end
    if fidw > 0
        try, fclose(fidw); catch, end
    end
end
end
