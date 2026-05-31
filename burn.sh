filepath=$(ls artifacts/result/iso/*.iso | head -n 1)
echo "Flashing $filepath to /dev/sda"
sudo dd if="$filepath" of=/dev/sda bs=4M status=progress oflag=sync