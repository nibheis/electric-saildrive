# Motor controller

This motor controller (VESC Maxim 120V from VescLabs) has been selected because it is a good match for the selected Engiro motor, but also because it features an open source firmware and the VESC community is very active.

In the main VESC folder, you will find the two LispBM scripts that runs on the 2 microcontrollers on the VESC Maxim.
- One microcontroller (STM32) is in charge of controlling the motor, and sending most data on the CAN/J1939 bus
- One microconttoller (ESP32) is in charge of controlling IOs (it receives the button press events from the throttle, and sends power to both the CAN bus and the N2K bus)

Both microcontollers are on the CAN bus and are communicating (e.g. when the throttle button is pressed, the ESP tells the STM to switch the maximum input current to a lower setting (eco mode).
