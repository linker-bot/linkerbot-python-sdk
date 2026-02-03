from linkerbot import L6

with L6("right", "can0") as hand:
    device_info = hand.version.get_device_info()
    print(f"Serial Number: {device_info.serial_number}")
    print(f"PCB Version: {device_info.pcb_version}")
    print(f"Firmware Version: {device_info.firmware_version}")
    print(f"Mechanical Version: {device_info.mechanical_version}")

    new_sn = "LHL6-03-129-R-Z-1-A"

    password = [0, 1, 2, 3, 4, 5]
    hand.version.set_serial_number(new_sn, password)

    device_info = hand.version.get_device_info()
    print(f"Serial Number: {device_info.serial_number}")
    print(f"PCB Version: {device_info.pcb_version}")
    print(f"Firmware Version: {device_info.firmware_version}")
    print(f"Mechanical Version: {device_info.mechanical_version}")

    assert device_info.serial_number == new_sn, (
        f"Serial number mismatch: {device_info.serial_number} != {new_sn}"
    )
