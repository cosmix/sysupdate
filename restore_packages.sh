#!/bin/bash
# Restore script for downgraded packages
# Generated automatically

set -e

echo "Restoring packages to latest versions..."

sudo apt-mark unhold bluez
echo "Unholding bluez..."
sudo apt-mark unhold cpio
echo "Unholding cpio..."

sudo apt update
sudo apt upgrade -y
echo "All packages restored!"
