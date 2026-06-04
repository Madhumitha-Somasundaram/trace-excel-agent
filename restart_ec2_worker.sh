#!/bin/bash

# Script to properly restart EC2 worker with cache clearing

echo "🛑 Stopping excel-worker service..."
sudo systemctl stop excel-worker

echo "🧹 Clearing Python cache..."
find /home/ec2-user/worker -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find /home/ec2-user/worker -type f -name "*.pyc" -delete 2>/dev/null || true

echo "⏳ Waiting 2 seconds..."
sleep 2

echo "🚀 Starting excel-worker service..."
sudo systemctl start excel-worker

echo "📊 Service status:"
sudo systemctl status excel-worker --no-pager

echo ""
echo "✅ Done! Check logs with:"
echo "   sudo journalctl -u excel-worker -f"
