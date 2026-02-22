#!/usr/bin/env bash

pip install -r requirements.txt

# install playwright browser in project directory
PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium