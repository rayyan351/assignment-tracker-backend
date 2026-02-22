#!/usr/bin/env bash

pip install -r requirements.txt

# install playwright browsers inside project
PLAYWRIGHT_BROWSERS_PATH=0 python -m playwright install chromium