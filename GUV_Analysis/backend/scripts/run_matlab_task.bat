@echo off
setlocal

set TASK_ID=%1
set RUN_ID=%2
set MODE=%3
set ND2_PATH=%4
set PARAMS_PATH=%5
set BASE_DIR=%6

:: Default Pipeline Root (can be overridden by Env Var)
if "%PIPELINE_ROOT%"=="" set PIPELINE_ROOT=G:\Trae_projects\GUV_Analysis\GUV_Analysis_V1.1.2

:: Default MATLAB Bin
if "%MATLAB_BIN%"=="" set MATLAB_BIN=D:\Matlab\Matlab\bin\matlab.exe

echo Starting MATLAB Task (Windows Batch): %TASK_ID% (%MODE%)
echo Pipeline: %PIPELINE_ROOT%

cd /d "%PIPELINE_ROOT%"

:: Construct MATLAB command
:: Note: Double quotes inside the command string need careful handling or just use single quotes for MATLAB strings
set CMD=addpath(genpath('%PIPELINE_ROOT%')); addpath(genpath('%~dp0')); run_matlab_task('%MODE%','%ND2_PATH%','%PARAMS_PATH%','%BASE_DIR%','%PIPELINE_ROOT%');

"%MATLAB_BIN%" -batch "%CMD%"
