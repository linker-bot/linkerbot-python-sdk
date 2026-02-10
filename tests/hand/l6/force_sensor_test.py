from linkerbot import L6
from linkerbot.hand.l6 import ForceSensorEvent, SensorSource

with L6("right", "can0") as hand:
    hand.start_polling(sources=[SensorSource.FORCE_SENSOR])
    for event in hand.stream():
        match event:
            case ForceSensorEvent(data=data):
                print(f"force sensor data: {data}")
