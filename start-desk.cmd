@echo off
rem Starts Claude Code in this folder with no permission prompts.
cd /d "%~dp0"
claude --dangerously-skip-permissions
