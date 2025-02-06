#!/usr/bin/env python

# Copyright (c) 2024 Antti Palosaari <crope@iki.fi>
#
# TE00AS43 Hardware Hacking and Reverse Engineering, Autumn 2024, 5 ECTS
#
# This application reads data from the Shimano EP800 e-bike motor bus using a
# Rigol MSO5000 series oscilloscope in a loop and writes it to stdout.
# The sample rate is 5 MSps, and the data format is a byte array.

# The user must set their oscilloscope's IP address in the MSO5000_ADDR
# variable.

import pyvisa
import time
import timeit
import sys

# XXX: There is some problems with line terminations, maybe backend bug. Use strip().
# XXX: Xfer rate is only about 4 Mbit/s. pyvisa backend?
# XXX: For 200M memory depth, it seems 5MSps is not possible for some strange reason. MSO5000 issue?
# XXX: Continous streaming is generally not possible with oscilloscope, so we lose a lot of data when trigger - transfer.

# Oscilloscope address. Please change.
MSO5000_ADDR = 'RIGOL_MS5A242105456.lan'

DEBUG = False

inst = pyvisa.ResourceManager().open_resource('TCPIP::{:s}::INSTR'.format(MSO5000_ADDR))
print(inst.query('*IDN?').strip())

'''
Possible combinations for 5MSps
:TIMebase:MAIN:SCALe / :ACQuire:MDEPth

  20ms /   1M (.2sec)
 200ms /  10M ( 2sec)
1000ms /  50M (10sec)
2000ms / 100M (20sec)
4000ms / 200M (40sec, 2RL option, still not working?)
'''

inst.write('*RST')
time.sleep(2)
inst.write(':CHANnel1:PROBe 10')
inst.write(':CHANnel1:COUPling AC')
inst.write(':CHANnel1:SCALe 150mV')
inst.write(':TRIGger:EDGE:LEVel 100mV')
inst.write(':TIMebase:MAIN:SCALe 200ms')
inst.write(':ACQuire:MDEPth 10M')
inst.write(':WAVeform:MODE RAW')
inst.write(':WAVeform:FORMat BYTE')

# First waveform is a bit like a banana if we don't wait a little. AC coupling?
time.sleep(4)

while True:
    inst.write(':TRIGger:SWEep SINGle')

    timeout = time.time() + 10  # 10 sec
    while True:
        trigger_status = inst.query(':TRIGger:STATus?').strip()
        if (DEBUG):
            print(trigger_status)
        if trigger_status == 'STOP':
            break
        elif time.time() > timeout:
            if (DEBUG):
                print('trigger timeout')
            break

    # Prevent timeouts
    inst.write(':STOP')

    start = timeit.default_timer()
    data = inst.query_binary_values(':WAVeform:DATA?', datatype='B', container=bytes)
    stop = timeit.default_timer()

    xfer_time = stop - start
    if (DEBUG):
        print('got {:d} bytes of waveform data in {:.2f} seconds, transfer speed {:.3f} kbit/s'.format(len(data), xfer_time, len(data)*8/xfer_time/1000))

    sys.stdout.buffer.write(data)
