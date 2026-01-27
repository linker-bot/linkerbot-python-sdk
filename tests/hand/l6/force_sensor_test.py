from linkerhand import L6

with L6("right", "can0") as hand:
    for data in hand.force_sensor.stream():
        print(f"force sensor data: {data}")
