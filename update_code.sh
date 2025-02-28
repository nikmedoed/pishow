#!/bin/bash

set -e

cd "$(dirname "$0")"

echo "Updating code..."
git pull origin main

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --no-cache-dir -r requirements.txt

echo "Restarting service..."
sudo systemctl restart pishow.service

echo "Done!"
