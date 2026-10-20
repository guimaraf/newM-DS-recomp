@echo off
title New Super Mario Bros. DS - Recomp Runner
cd /d "%~dp0dist-playable"
start "" "nds_runner.exe" . --interactive --rom "New Super Mario Bros. (USA).nds" --fps-limit 60 --boot direct --freebios --generated-firmware --screen-layout stacked
