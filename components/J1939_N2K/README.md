# CAN J1939 to NMEA2000 adaptor

Here are some information on the CAN/J1939 bus (used in the automotive industry). This CAN bus is used to transport information about the engine - usually an internal combustion engine.
This CAN bus is also used on boat engines; this is good for us because it means that we can find gateways to translate CAN/J1939 data to NMEA2000 data, directly off the shelf.

Veratron's LinkUp J1939/NMEA2000 is one of them.

The VESC controller is running a LispBM script that collects data from the motor, the controller itself, and transmit this data (RPM, temperatures, ...) in CAN/J1939 format to the gateway, which transmits the same data in NMEA2000 format, so that a standard NMEA2000 display can show this data. It's been validated with a Garmin TD50 display ; any other NME2000 display (that can show engine data) should work.

Note #1: Veratron's LinkUp can manage up to 2 engines (ECUs) on the CAN bus. The first ECU on the CAN/J1939 has to have Source Address 0x00.

Note #2: Veratron's LinkUp, like most gateways, expects CAN data on specific PGNs (messages). It is not possible to use a new message to transport 'ECU temperature' ; the gateway will just ignore it. This is why the VESC script is mapping the motor temperature to 'coolant temperature' and the VESC temperature to 'oil temperature'. On the NMEA display, both temperatures appear as coolant and oil temperature.
