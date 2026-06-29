# import the library
import can

# create a bus instance using 'with' statement,
# this will cause bus.shutdown() to be called on the block exit;
# many other interfaces are supported as well (see documentation)
with can.Bus(interface='socketcan', channel='can0', receive_own_messages=True) as bus:
    ## Send a message
    #message = can.Message(arbitration_id=123, is_extended_id=True, data=[0x11, 0x22, 0x33])
    #bus.send(message, timeout=0.2)

    # Iterate over received messages
    for msg in bus:
        data = ':'.join(f'{x:02X}' for x in msg.data)
        #data_ascii = '|'
        #for x in msg.data:
        #    if (x >= 0x20 and x <= 0x7E):
        #        data_ascii += ' '+chr(x)
        #    else:
        #        data_ascii += f'{x:02X}'
        #    data_ascii += '|'
        print(f"{msg.arbitration_id:X}:{data}", flush=True)

    # ... Or use an asynchronous notifier
    #notifier = can.Notifier(bus, [can.Logger("recorded.log"), can.Printer()])

# EOF
