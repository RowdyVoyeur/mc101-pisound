#!/bin/bash

echo "Configuring M8 udev rules..."
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="16c0", ATTR{idProduct}=="048a", MODE="0666", GROUP="plugdev"' | sudo tee /etc/udev/rules.d/50-m8.rules > /dev/null

sudo udevadm control --reload-rules
sudo udevadm trigger

echo "Configuring Pisound Button..."

# 1. Copy the scripts from the repository to the Pisound system folder
sudo cp /home/patch/mc101-pisound/patchbox-module/pisound-btn/audio_routing.sh /usr/local/pisound/scripts/pisound-btn/
sudo cp /home/patch/mc101-pisound/patchbox-module/pisound-btn/reset.sh /usr/local/pisound/scripts/pisound-btn/
sudo cp /home/patch/mc101-pisound/patchbox-module/pisound-btn/reboot.sh /usr/local/pisound/scripts/pisound-btn/

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

echo "Install complete!"