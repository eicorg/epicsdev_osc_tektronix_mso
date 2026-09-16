# Reset USB controller
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
