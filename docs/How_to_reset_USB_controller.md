# Reset USB
## Reset a Single USB Device
```
ls usb
```
Use the usbreset utility (if installed via sudo apt install usbutils) by pointing it to the device path:
```
sudo usbreset /dev/bus/usb/BUS_NUM/DEV_NUM
# Alternatively, toggle the authorization state in the system files:
echo 0 | sudo tee /sys/bus/usb/devices/DEVICE_ID/authorized
echo 1 | sudo tee /sys/bus/usb/devices/DEVICE_ID/authorized
```

## Reset the USB Controller (All Ports)
Find the controller ID:
```
lspci -D | grep USB
```
Unbind and rebind the controller (replace 0000:00:14.0 with your actual bus ID):
```
echo 0000:00:14.0 | sudo tee /sys/bus/pci/drivers/xhci_hcd/unbind
sleep 3
echo 0000:00:14.0 | sudo tee /sys/bus/pci/drivers/xhci_hcd/bind
```
