# epike_bus_dump

This application demodulates and decodes data from the Shimano EP800 e-bike bus.

## Usage examples
```$ ./mso5000.py | ./epike_bus_dump.py```

```$ rtl_sdr -f 0 -s 3200000 -D - | sox -r 3200000 -t raw -e unsigned -b 8 -c 2 - -r 5000000 -t raw -e unsigned -b 8 -c 1 - remix 1 | ./epike_bus_dump.py```

```$ cat ep800_poweron_sniff.bin | ./epike_bus_dump.py```

It doesn't matter how the data is sampled from the bus as long as it is in the correct format for the application: 5 MSps unsigned byte.
The signal's carrier frequency is 1 MHz, which is relatively high, and sampling it properly requires an ADC capable of 3–4 MSps. Such high-speed ADCs are relatively uncommon; suitable ones can be found in oscilloscopes and SDR receivers.


## Decoder example outputs
```
2025-02-06 19:12:04.677760 [decod] ID 1a | datetime: 2025-02-06 19:12:13
2025-02-06 19:51:38.071240 [decod] ID 1a | range: 61/92/184 km (boost/trail/eco)
2025-02-06 20:11:58.837892 [decod] ID 1a | ODO (total distance): 3813610 m
2025-02-06 20:11:58.824296 [decod] ID 1a | DST (trip distance): 30567 m
2025-02-06 20:12:25.267182 [decod] ID 0d | trip time: 116 min
2025-02-06 20:12:00.593327 [decod] ID 0d | assist mode: 0 (0=off, 1=eco, 2=trail, 3=boost)
2025-02-06 20:12:32.959078 [decod] ID 1a | walk mode: 1 (0=off, 1=on, 2=active)
2025-02-06 20:12:11.313870 [decod] ID 1a | speed: 11.4 km/h
2025-02-06 20:12:11.408166 [decod] ID 0d | max speed: 32.0 km/h
2025-02-06 20:12:25.264026 [decod] ID 0d | avg speed: 15.7 km/h
2025-02-06 20:12:21.786540 [decod] ID 0d | cadence: 58 rpm
2025-02-06 20:12:28.182133 [decod] ID 26 | switch upper pressed
2025-02-06 20:12:28.272870 [decod] ID 26 | switch upper keep hold down
2025-02-06 20:12:28.414347 [decod] ID 26 | switch upper released from hold
2025-02-06 20:19:30.241056 [decod] ID 0d | battery: 60 %
```


## Demulation + decoder example output
```
2025-02-06 19:51:06.671734 [demod] ID 3f | CRC OK  | ce 3f 81 8a 4a 00 19 d7 | 10001010 01001010 00000000 00011001 | 138  74   0  25 | .J.. | FF | 10 | 0
2025-02-06 19:51:06.672851 [demod] ID 3f | CRC OK  | ce 3f 81 0b 02 06 13 6f | 00001011 00000010 00000110 00010011 |  11   2   6  19 | .... | CF | 11 | 0
2025-02-06 19:51:06.673968 [demod] ID 3f | CRC OK  | ce 3f 81 4c 33 25 ff 07 | 01001100 00110011 00100101 11111111 |  76  51  37 255 | L3%. | LF | 12 | 0
2025-02-06 19:51:06.674017 [decod] ID 3f | packet: 4a 00 19 02 06 13 33 25 ff
2025-02-06 19:51:06.674017 [decod] ID 3f | datetime: 2025-02-06 19:51:37
```

## Interfacing the E-tube bus
Buy a Shimano EW-SD300 cable, cut it in half. The cable has a red and black conductor. Use a small series capacitor on the red conductor to block DC if the receiver does not have one (DC/AC coupling). The size of the capacitor is not critical, for example, 100nF works well.

The cable can be attached to any free port, for example, to the motor or the display. There are several ports on the back of the display, which is often the easiest place to connect it.

## Happy hacking!
Although I only tested the program with the EP800 motor, it might work with all motors manufactured by Shimano and perhaps even with Di2 shifters. The decoder probably doesn't recognize all messages from other systems, but they are easy to add. Patches are welcome.
