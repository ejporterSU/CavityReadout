'''
Created on 04.11.2020

@author: mattkatz
'''
import ctypes 
import numpy as np 
import ipaddress


def convertSerialNumberToUINT32(SerialNumberPart):  
    sNuint8=(np.fromstring(SerialNumberPart[::-1], dtype=np.uint8)) #reverse it and convert it to uint8
    return int(np.frombuffer(sNuint8, dtype=np.uint32))
    
class T_Interface:
    T_Interface_USBFirstFound = ctypes.c_uint16(0)
    T_Interface_EthernetFirstFound = ctypes.c_uint16(1)
    T_Interface_EthernetIPAddress = ctypes.c_uint16(2)
    T_Interface_EthernetOrUSBUseSerialNumber = ctypes.c_uint16(3)
    T_Interface_EthernetOrUSBFirstFound = ctypes.c_uint16(4)

class T_InterfaceSpec(ctypes.Structure):
    _fields_ = [("Source", ctypes.c_uint16),
                ("TCPAdr", ctypes.c_uint32),
                ("TCPPort", ctypes.c_uint32),
                ("CAUSerNumHi", ctypes.c_uint32),
                ("CAUSerNumLo", ctypes.c_uint32)
                ]


    def __init__(self, Source, IPAddr, TCP_Port, SerialNumber):
        self.Source=Source 
        self.TCPAdr=ctypes.c_uint32((int(ipaddress.IPv4Address(IPAddr))))
        self.TCPPort=ctypes.c_uint32(TCP_Port)
        self.CAUSerNumHi=ctypes.c_uint32(convertSerialNumberToUINT32(SerialNumber.rjust(8, '\0')[0:4]))
        self.CAUSerNumLo=ctypes.c_uint32(convertSerialNumberToUINT32(SerialNumber.rjust(8, '\0')[4:8]))