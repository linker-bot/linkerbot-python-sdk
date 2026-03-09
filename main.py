from linkerbot import L25

with L25("left", "can0") as hand:
    print(hand.version.get_device_info())
