function AllXYResults = guvCompute_collectAllXYResults(OutRoot, SeriesPrefix)
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

    outCsv = fullfile(OutRoot, 'AllXYResults.csv');
    [outDir,~,~] = fileparts(outCsv);
    if ~isempty(outDir) && ~exist(outDir,'dir')
        mkdir(outDir);
    end

    [ok, hdrVars, hdrVarsValid] = localStreamCollectAllResults(files, outCsv, SeriesPrefix);
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

function [ok, headerVars, headerVarsValid] = localStreamCollectAllResults(files, outCsv, SeriesPrefix)
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
        headerVars = [vars, {'GlobalID'}];
        headerVarsValid = cell(size(headerVars));
        for k = 1:numel(headerVars)
            v = headerVars{k};
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
        if seriesIdx == 0 || seriesIdx > 0 && isempty(strtrim(parts{seriesIdx}))
            if seriesIdx > 0
                parts{seriesIdx} = xyName;
            end
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
