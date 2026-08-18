@echo off
REM Double-click this to fetch the latest synced data and open the dashboard.
cd /d "%~dp0"

echo Fetching latest data from GitHub...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo Could not pull. If you have local changes, that is the usual cause.
  echo Opening the dashboard you already have instead.
  echo.
)

start "" "docs\index.html"
