'''
Created on 23.11.2020

@author: mattkatz
'''
import ctypes

class T_T0dt(ctypes.Structure):
    _fields_ = [("T0", ctypes.c_double),
                ("dt", ctypes.c_double),
                ("n", ctypes.c_int32),
                ("TTrig", ctypes.c_double),
                ("Frame", ctypes.c_int32),
                ("NumFrames", ctypes.c_int32)
                ]

    def __init__(self):
        self.T0 = ctypes.c_double(0) 
        self.dt = ctypes.c_double(0)
        self.n = ctypes.c_int32(0)
        self.TTrig = ctypes.c_double(0)
        self.Frame = ctypes.c_int32(0)
        self.NumFrames = ctypes.c_int32(0)
    def reset(self):
        self.T0 = ctypes.c_double(0)
        self.dt = ctypes.c_double(0)
        self.n = ctypes.c_int32(0)
        self.TTrig = ctypes.c_double(0)
        self.Frame = ctypes.c_int32(0)
        self.NumFrames = ctypes.c_int32(0)
        