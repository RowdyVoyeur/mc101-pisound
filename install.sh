#!/bin/bash

echo "Configuring M8 udev rules..."
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="16c0", ATTR{idProduct}=="048a", MODE="0666", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/50-m8.rules > /dev/null

sudo udevadm control --reload-rules
sudo udevadm trigger

echo "Configuring Pisound Button..."
# 1. Copy the scripts from the repository to the Pisound system folder
sudo cp /home/patch/mc101-pisound/pisound-btn/audio_routing.sh /usr/local/pisound/scripts/pisound-btn/
sudo cp /home/patch/mc101-pisound/pisound-btn/reset.sh /usr/local/pisound/scripts/pisound-btn/
sudo cp /home/patch/mc101-pisound/pisound-btn/reboot.sh /usr/local/pisound/scripts/pisound-btn/

# 2. Make them executable by everyone
sudo chmod 755 /usr/local/pisound/scripts/pisound-btn/audio_routing.sh
sudo chmod 755 /usr/local/pisound/scripts/pisound-btn/reset.sh
sudo chmod 755 /usr/local/pisound/scripts/pisound-btn/reboot.sh

# 3. Update the Pisound configuration file directly
CONF="/etc/pisound.conf"
sudo sed -i 's|^CLICK_1.*|CLICK_1 /usr/local/pisound/scripts/pisound-btn/audio_routing.sh|' $CONF
sudo sed -i 's|^CLICK_2.*|CLICK_2 /usr/local/pisound/scripts/pisound-btn/audio_routing.sh|' $CONF
sudo sed -i 's|^CLICK_3.*|CLICK_3 /usr/local/pisound/scripts/pisound-btn/audio_routing.sh|' $CONF
sudo sed -i 's|^CLICK_OTHER.*|CLICK_OTHER /usr/local/pisound/scripts/pisound-btn/audio_routing.sh|' $CONF

sudo sed -i 's|^HOLD_1S.*|HOLD_1S /usr/local/pisound/scripts/pisound-btn/reset.sh|' $CONF
sudo sed -i 's|^HOLD_3S.*|HOLD_3S /usr/local/pisound/scripts/pisound-btn/reboot.sh|' $CONF

# 4. Restart the button service to apply the new mappings
sudo systemctl restart pisound-btn

echo "Disabling telemetry, Wi-Fi hotspot, and unnecessary MIDI services..."
sudo systemctl disable --now blokas-telemetry.target
sudo systemctl disable --now wifi-hotspot.service
sudo systemctl disable --now touchosc2midi.service

echo "Disabling PulseAudio to free up resources..."
# We must execute this as the patch user with the correct environment variables
sudo -u patch XDG_RUNTIME_DIR=/run/user/$(id -u patch) systemctl --user stop pulseaudio.socket pulseaudio.service
sudo -u patch XDG_RUNTIME_DIR=/run/user/$(id -u patch) systemctl --user disable pulseaudio.socket pulseaudio.service
sudo -u patch XDG_RUNTIME_DIR=/run/user/$(id -u patch) systemctl --user mask pulseaudio.socket pulseaudio.service

echo "Setting Locale to en_US.UTF-8..."
sudo sed -i 's/^# *\(en_US.UTF-8\)/\1/' /etc/locale.gen
sudo locale-gen en_US.UTF-8
sudo update-locale LC_ALL="en_US.UTF-8" LANGUAGE="en_US"

echo "Optimizing /boot/config.txt (Disabling Onboard Audio, BT, and Wi-Fi)..."
BOOT_CONFIG="/boot/config.txt"

# Disable onboard audio (replace dtparam=audio=on with dtparam=audio=off)
sudo sed -i 's/^dtparam=audio=on/dtparam=audio=off/' $BOOT_CONFIG
# If it wasn't there at all, append it
grep -q "^dtparam=audio=off" $BOOT_CONFIG || echo "dtparam=audio=off" | sudo tee -a $BOOT_CONFIG > /dev/null

# Disable HDMI audio
sudo sed -i 's/^dtoverlay=vc4-kms-v3d$/dtoverlay=vc4-kms-v3d,noaudio/' $BOOT_CONFIG

# Disable Bluetooth and Wi-Fi
grep -q "^dtoverlay=disable-bt" $BOOT_CONFIG || echo "dtoverlay=disable-bt" | sudo tee -a $BOOT_CONFIG > /dev/null
grep -q "^dtoverlay=disable-wifi" $BOOT_CONFIG || echo "dtoverlay=disable-wifi" | sudo tee -a $BOOT_CONFIG > /dev/null

echo "Install complete! A reboot is highly recommended to apply config.txt and locale changes."