# CAN J1939 to NMEA2000 adaptor

Here are some information on the CAN/J1939 bus (used in the automotive industry). This CAN bus is used to transport information about the engine - usually an internal combustion engine.
This CAN bus is also used on boat engines; this is good for us because it means that we can find gateways to translate CAN/J1939 data to NMEA2000 data, directly off the shelf.

Veratron's LinkUp J1939/NMEA2000 is one of them.

The VESC controller is running a LispBM script that collects data from the motor, the controller itself, and transmit this data (RPM, temperatures, ...) in CAN/J1939 format to the gateway, which transmits the same data in NMEA2000 format, so that a standard NMEA2000 display can show this data. It's been validated with a Garmin TD50 display ; any other NME2000 display should work.
