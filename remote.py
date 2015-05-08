import serial
import sys

s = serial.Serial('/dev/ttyAMA0', timeout=.1, baudrate=9600)

s.write('%s\r' % sys.argv[1])
print '%s: %s' % (sys.argv[1], s.read(512))

