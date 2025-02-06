#!/usr/bin/env python

# Copyright (c) 2024 Antti Palosaari <crope@iki.fi>
#
# TE00AS43 Hardware Hacking and Reverse Engineering, Autumn 2024, 5 ECTS
#
# This application demodulates and decodes data from the Shimano EP800
# e-bike bus. The application receives data sampled at a 5 MSps rate
# from the stdin input, demodulates it, and decodes it.

import numpy as np
import scipy
import matplotlib.pyplot as plt
import sys
import crcmod
import datetime

# Signal is BPSK modulation over Power Line.
# Carrier frequency is 1 MHz, data rate is 500 kbit/sec. Each symbol is
# repeated twice, meaning symbol length is 2 lambdas.
# The symbol is 2 lambda long! Repeated! Redundancy!

ADC_SAMPLE_RATE = int(5000000)
DEMOD_SAMPLE_RATE = int(1 * ADC_SAMPLE_RATE)
BPSK_SYMBOL_RATE = int(500000)
SAMPLES_PER_SYMBOL = int(DEMOD_SAMPLE_RATE / BPSK_SYMBOL_RATE)
ADC_SAMPLES_FOR_3_BYTE_MSG = int(ADC_SAMPLE_RATE / BPSK_SYMBOL_RATE * 8 * 3)
ADC_SAMPLES_FOR_TOO_LONG_MSG = int(ADC_SAMPLE_RATE / BPSK_SYMBOL_RATE * 8 * 20)

# Filter OUT these packets
MSG_FILTER = [
    # Flow control?, watchdog? ~500us intervals
    # XXX: Is that demodulated wrong? cf 7f 81 => cc bf 81?
    np.frombuffer(bytes.fromhex('cf 7f 81'), dtype=np.uint8),

    # Unknow 3 byte messages. Some of these are probably demodulation errors.
    np.frombuffer(bytes.fromhex('cc 80 9a'), dtype=np.uint8),
    np.frombuffer(bytes.fromhex('cc 8d 01'), dtype=np.uint8),
    np.frombuffer(bytes.fromhex('cc 93 01'), dtype=np.uint8),
    np.frombuffer(bytes.fromhex('cf 7f 80'), dtype=np.uint8),
    np.frombuffer(bytes.fromhex('cc 80 a6'), dtype=np.uint8),
]


def main():
    count_msg = 0
    count_crc_err = 0
    crc_func = crcmod.mkCrcFun(0b100000111, initCrc=0x6f, xorOut=0x00, rev=False)
    data_packets = {}

    print('ADC_SAMPLE_RATE: %d (real)' % (ADC_SAMPLE_RATE))
    print('DEMOD_SAMPLE_RATE: %d (real)' % (DEMOD_SAMPLE_RATE))
    print('BPSK_SYMBOL_RATE: %d' % (BPSK_SYMBOL_RATE))
    print('SAMPLES_PER_SYMBOL: %d' % (SAMPLES_PER_SYMBOL))
    print('ADC_SAMPLES_FOR_3_BYTE_MSG: %d' % (ADC_SAMPLES_FOR_3_BYTE_MSG))
    print('ADC_SAMPLES_FOR_TOO_LONG_MSG: %d' % (ADC_SAMPLES_FOR_TOO_LONG_MSG))

    NOISE_THRESHOLD = 256 * 0.034
    NOISE_THRESHOLD_MAX = round(255 / 2 + NOISE_THRESHOLD)
    NOISE_THRESHOLD_MIN = round(255 / 2 - NOISE_THRESHOLD)

    while True:
        data = np.empty(0, dtype=np.uint8)
        buf = np.empty(0, dtype=np.uint8)

        while True:
            buf = np.frombuffer(sys.stdin.buffer.read(32), dtype=np.uint8)

            if (buf.size == 0):
                print('total msg count: %d' % (count_msg))
                print('CRC error msg count: %d' % (count_crc_err))
                exit()
            elif (buf.min() < NOISE_THRESHOLD_MIN or buf.max() > NOISE_THRESHOLD_MAX):
                # This is performance bottleneck! minmax()...
                # Larger the buf we use the faster that is, but demodulation errors increases
                data = np.append(data, buf)
            elif (data.size >= ADC_SAMPLES_FOR_3_BYTE_MSG and data.size < ADC_SAMPLES_FOR_TOO_LONG_MSG):
                break
            else:
                data = np.empty(0, dtype=np.uint8)

        PEAK_MIN = data.min()
        PEAK_MAX = data.max()
        MEAN = data.mean()

        if 0:
            plt.title("Raw frame and sample points")
            plt.plot(data)
            plt.plot(data, "x", color='r')
            plt.tight_layout()
            plt.show()

        # peaks, highs and lows
        data_inv = np.subtract(255, data)

        PEAK = 0.87 * PEAK_MAX
        peaks_hi = scipy.signal.find_peaks(data, height=PEAK)[0]
        PEAK = 0.87 * (255 - PEAK_MIN)
        peaks_lo = scipy.signal.find_peaks(data_inv, height=PEAK)[0]

        if 0:
            plt.title("Peaks detected")
            plt.plot(data)
            plt.plot(peaks_hi, data[peaks_hi], "x", color='r')
            plt.plot(peaks_lo, data[peaks_lo], "o", color='r')
            plt.tight_layout()
            plt.show()

        # Invert signal data - it is easier to handle if signal curve starts from negative value to positive
        if peaks_hi[0] < peaks_lo[0]:
            data = data_inv
            peaks_hi, peaks_lo = peaks_lo, peaks_hi

            if 0:
                plt.title("Peaks detected - inverted curve")
                plt.plot(data)
                plt.plot(peaks_hi, data[peaks_hi], "x", color='r')
                plt.plot(peaks_lo, data[peaks_lo], "o", color='r')
                plt.tight_layout()
                plt.show()

        # Detect signal start and end. Those are first and last peaks, enough for that case
        x_first = min(peaks_hi[0], peaks_lo[0])
        x_last = max(peaks_hi[-1], peaks_lo[-1])

        # Symbol to bit mapping
        bits = []
        peaks = []
        for i in range(x_first, x_last, SAMPLES_PER_SYMBOL):
            y = data[i]
            bits.append(y < MEAN)
            # Debug
            peaks.append(i)

        if 0:
            plt.title("Points used by demod to make symbol decision")
            plt.plot(data)
            plt.plot(peaks, data[peaks], "o", color='r')
            plt.tight_layout()
            plt.show()

        # Remove SOF start of frame bit
        bits = bits[1:]

        # Bits to bytes
        data_frame = np.packbits(bits)
        count_msg += 1

        #####################################################################
        # Parse some data from demodulated data frames

        # Check CRC. Valid only 3 bytes msg or more
        if (data_frame.size <= 3):
            crc_text = 'N/A'
        elif (crc_func(data_frame[:-1]) == data_frame[-1]):
            crc_text = 'OK '
        else:
            crc_text = 'ERR'
            count_crc_err += 1

        # Resolve device id (~CAN ID)
        # Message header
        dev_id = False
        if (data_frame.size >= 3):
            if (data_frame[0] == 0xcc):
                if (data_frame[1] == 0x40):
                    # normal broadcast
                    dev_id = (data_frame[2] >> 0) & 0x3f

                elif ((data_frame[1] & 0x80) >> 7):
                    # remote transmission request ?
                    dev_id = (data_frame[1] >> 0) & 0x3f

            elif (data_frame[0] == 0xce):
                # remote transmission reply ?

                # 2 uppermost bits on byte[1] are zero, but no check now...
                dev_id = (data_frame[1] >> 0) & 0x3f

        # Combine multi-frame messages. Combined messages are feed for the decoder.
        # TODO: Check message seq numbers
        dev_id_data_packet_complete = None
        if dev_id and data_frame.size == 8:
            key = dev_id

            frame_type = (data_frame[3] >> 6) & 0x03  # [7:6]
            reserved   = (data_frame[3] >> 5) & 0x01  # [5:5]
            counter    = (data_frame[3] >> 0) & 0x1f  # [4:0]

            match frame_type:
                case 0b00:
                    # Consecutive Frame (CF)
                    frame_type_str = 'CF'
                    if key in data_packets.keys():
                        data_packets[key] = np.append(data_packets[key], data_frame[4:7])
                case 0b01:
                    # Last Frame (LF)  ** CAN-TP/ISO-TP does not have such frame
                    frame_type_str = 'LF'
                    if key in data_packets.keys():
                        data_packets[key] = np.append(data_packets[key], data_frame[4:7])
                        dev_id_data_packet_complete = key
                case 0b10:
                    # First Frame (FF)
                    frame_type_str = 'FF'
                    data_packets[key] = data_frame[4:7]
                case 0b11:
                    # Single Frame (SF)
                    frame_type_str = 'SF'
                    data_packets[key] = data_frame[4:7]
                    dev_id_data_packet_complete = key
                case _:
                    pass

        # Print demodulated data frames
        if not any(np.array_equal(data_frame[:3], msg) for msg in MSG_FILTER):
            DEMOD_LOG_HDR = '{:s} [demod] ID {:02x} |'.format(str(datetime.datetime.now()), dev_id)

            # 3 and 8 bytes are normal data frame sizes, others are likely demodulation errors
            if (data_frame.size < 8):
                print(DEMOD_LOG_HDR,
                      'CRC {:s}'.format(crc_text),
                      '|',
                      ''.join(' '.join('{:02x}'.format(x) for x in data_frame)),  # hex dump
                      '|',
                      ''.join(' '.join('{:08b}'.format(x) for x in data_frame)),  # bin dump
                      )
            else:
                print(DEMOD_LOG_HDR,
                      'CRC {:s}'.format(crc_text),
                      '|',
                      ''.join(' '.join('{:02x}'.format(x) for x in data_frame)),  # hex dump
                      '|',
                      ''.join(' '.join('{:08b}'.format(x) for x in data_frame[3:-1])),  # bin dump
                      '|',
                      ''.join(' '.join('{:3d}'.format(x) for x in data_frame[3:-1])),  # dec dump
                      '|',
                      ''.join(''.join('{:c}'.format(x if 32 <= x < 127 else ord('.')) for x in data_frame[3:-1])),  # ascii dump
                      '|',
                      '{:s}'.format(frame_type_str),
                      '|',
                      '{:2d}'.format(counter),
                      '|',
                      '{:01b}'.format(reserved),
                      )

        #####################################################################
        # Frame decoder
        key = dev_id_data_packet_complete

        if key:
            cmd = (key << 16) | int.from_bytes(data_packets[key][0:2], byteorder='big', signed=False)
            DECODER_LOG_HDR = '{:s} [decod] ID {:02x} |'.format(str(datetime.datetime.now()), key)
            print(DECODER_LOG_HDR, 'packet:', ''.join(' '.join('{:02x}'.format(x) for x in data_packets[key])))  # hex dump

            match cmd:
                case 0x0d4a0c:
                    if np.array_equal(data_packets[key], np.frombuffer(bytes.fromhex('4a 0c ff'), dtype=np.uint8)):
                        # 0d | 4a 0c ff
                        # unknown static data frame
                        continue

                case 0x1a0102:
                    if np.array_equal(data_packets[key], np.frombuffer(bytes.fromhex('01 02 ff'), dtype=np.uint8)):
                        # 1a | 01 02 ff
                        # unknown static data frame
                        continue

                case 0x260102:
                    if np.array_equal(data_packets[key], np.frombuffer(bytes.fromhex('01 02 ff'), dtype=np.uint8)):
                        # 26 | 01 02 ff
                        # unknown static data frame
                        continue

                case 0x3f0200:
                    if np.array_equal(data_packets[key], np.frombuffer(bytes.fromhex('02 00 40'), dtype=np.uint8)):
                        # 3f | 02 00 40
                        # unknown static data frame
                        continue

                case 0x3f0208:
                    if np.array_equal(data_packets[key], np.frombuffer(bytes.fromhex('02 08 01'), dtype=np.uint8)):
                        # 3f | 02 08 01
                        # unknown static data frame
                        continue

                case 0x0d1638 | \
                     0x1a163a:
                    # 0d | 16 3a 38 02 ff ff
                    # 1a | 16 3a 1a 02 ff ff
                    # max speed
                    val = int.from_bytes(data_packets[key][2:4], byteorder='little', signed=False) / 10
                    print(DECODER_LOG_HDR, 'max speed: {:.1f} km/h'.format(val))
                    del data_packets[key]

                case 0x3f4a00 | \
                     0x1a4a0e:
                    # 3f | 4a 00 18 0c 14 05 22 06 ff
                    # 1a | 4a 0e 18 0c 0c 00 1e 0d ff
                    # datetime yy mm dd hh mm ss
                    val0 = int.from_bytes(data_packets[key][2:3], byteorder='little', signed=False) + 2000
                    val1 = int.from_bytes(data_packets[key][3:4], byteorder='little', signed=False)
                    val2 = int.from_bytes(data_packets[key][4:5], byteorder='little', signed=False)
                    val3 = int.from_bytes(data_packets[key][5:6], byteorder='little', signed=False)
                    val4 = int.from_bytes(data_packets[key][6:7], byteorder='little', signed=False)
                    val5 = int.from_bytes(data_packets[key][7:8], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'datetime: {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}'.format(val0, val1, val2, val3, val4, val5))
                    del data_packets[key]

                case 0x0d1620 | \
                     0x1a1622:
                    # 0d | 16 20 3d 00 5c 00 b8 00 ff
                    # 1a | 16 22 3d 00 5c 00 b8 00 ff
                    # range
                    val0 = int.from_bytes(data_packets[key][2:4], byteorder='little', signed=False)  # boost
                    val1 = int.from_bytes(data_packets[key][4:6], byteorder='little', signed=False)  # trail
                    val2 = int.from_bytes(data_packets[key][6:8], byteorder='little', signed=False)  # eco
                    print(DECODER_LOG_HDR, 'range: {:d}/{:d}/{:d} km (boost/trail/eco)'.format(val0, val1, val2))
                    del data_packets[key]

                case 0x0d3c08 | \
                     0x1a3c0a:
                    # 0d | 3c 08 1a 02 00 ff
                    # 1a | 3c 0a 25 02 00 ff
                    # speed
                    val = int.from_bytes(data_packets[key][2:4], byteorder='little', signed=False) / 10
                    print(DECODER_LOG_HDR, 'speed: {:.1f} km/h'.format(val))
                    del data_packets[key]

                case 0x0d4808 | \
                     0x1a480a:
                    # 0d | 48 08 e6 67 00 00
                    # 1a | 48 0a 09 68 00 00
                    # DST (trip distance)
                    val = int.from_bytes(data_packets[key][2:6], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'DST (trip distance): {:d} m'.format(val))
                    del data_packets[key]

                case 0x0d4828 | \
                     0x1a482a:
                    # 0d | 48 28 93 a6 3b 00
                    # 1a | 48 2a 93 a6 3b 00
                    # ODO (total distance)
                    val = int.from_bytes(data_packets[key][2:6], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'ODO (total distance): {:d} m'.format(val))
                    del data_packets[key]

                case 0x0d3848 | \
                     0x1a384a:
                    # 0d | 38 48 00 00 67 ff
                    # 1a | 38 4a 00 00 67 ff
                    # cadence
                    val = int.from_bytes(data_packets[key][4:5], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'cadence: {:d} rpm'.format(val))
                    del data_packets[key]

                case 0x0d1628 | \
                     0x1a162a:
                    # 0d | 16 28 7b 00 00 00
                    # 1a | 16 2a 7b 00 00 00
                    # trip time
                    val = int.from_bytes(data_packets[key][2:6], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'trip time: {:d} min'.format(val))
                    del data_packets[key]

                case 0x0d1630 | \
                     0x1a1632:
                    # 0d | 16 30 81 00 ff ff
                    # 1a | 16 32 81 00 ff ff
                    # average speed
                    val = int.from_bytes(data_packets[key][2:4], byteorder='little', signed=False) / 10
                    print(DECODER_LOG_HDR, 'avg speed: {:.1f} km/h'.format(val))
                    del data_packets[key]

                case 0x0d1600 | \
                     0x1a1602:
                    # 0d | 16 00 02 00 ff ff
                    # 1a | 16 02 01 00 ff ff
                    # assist mode (0=off, 1=eco, 2=trail, 3=boost)
                    val = int.from_bytes(data_packets[key][2:4], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'assist mode: {:d} (0=off, 1=eco, 2=trail, 3=boost)'.format(val))
                    del data_packets[key]

                case 0x0d1660 | \
                     0x1a1662 | \
                     0x131660 | \
                     0x261662:
                    # 0d | 16 60 00
                    # 1a | 16 62 02
                    # 13 | 16 60 00
                    # 26 | 16 62 00
                    # walk mode (0=off, 1=on, 2=active)
                    val = int.from_bytes(data_packets[key][2:3], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'walk mode: {:d} (0=off, 1=on, 2=active)'.format(val))
                    del data_packets[key]

                case 0x0d0400 | \
                     0x260400:
                    # 0d | 04 00 07
                    # 26 | 04 00 27
                    # switch
                    if ((data_packets[key][2] >> 0) & 0x01):
                        str0 = 'lower'
                    else:
                        str0 = 'upper'

                    match (data_packets[key][2] >> 4) & 0x03:
                        case 0:
                            str1 = 'pressed'
                        case 1:
                            str1 = 'released from hold'
                        case 2:
                            str1 = 'keep hold down'

                    print(DECODER_LOG_HDR, 'switch {:s} {:s}'.format(str0, str1))
                    del data_packets[key]

                case 0x0d2640 | \
                     0x1a2642:
                    # 0d | 26 40 64
                    # 1a | 26 42 64
                    # battery %
                    val = int.from_bytes(data_packets[key][2:3], byteorder='little', signed=False)
                    print(DECODER_LOG_HDR, 'battery: {:d} %'.format(val))
                    del data_packets[key]

                case _:
                    # unknown message cannot decode
                    print(DECODER_LOG_HDR,
                          'unknown:',
                          ''.join(' '.join('{:02x}'.format(x) for x in data_packets[key])),  # hex dump
                          '|',
                          ''.join(''.join('{:c}'.format(x if 32 <= x < 127 else ord('.')) for x in data_packets[key])),  # ascii dump
                          )
                    del data_packets[key]


if __name__ == "__main__":
    main()
