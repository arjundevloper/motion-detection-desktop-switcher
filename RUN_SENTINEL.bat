@echo off
title ARJUN SUS Setup
echo.
echo  Installing dependencies...
pip install -r requirements.txt --quiet

echo  Launching ARJUN SUS...
:: pythonw = windowless Python, no console appears at all
start "" pythonw sentinel.py
