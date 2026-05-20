@echo off
REM Compatibility shim for automation that invokes venv/Scripts/python.exe through cmd.exe.
REM cmd treats the forward slash as an argument separator and executes "venv";
REM discard that synthetic first argument and delegate to the real venv Python.
if /I "%~1"=="/Scripts/python.exe" shift
if /I "%~1"=="\Scripts\python.exe" shift
if /I "%~1"=="Scripts\python.exe" shift
if /I "%~1"=="Scripts/python.exe" shift
"venv\Scripts\python.exe" %1 %2 %3 %4 %5 %6 %7 %8 %9
