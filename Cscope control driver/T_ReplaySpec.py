'''
Created on 06.11.2020

@author: mattkatz
'''
import ctypes

class T_ReplaySpec(ctypes.Structure):
    _fields_ = [("StartTime", ctypes.c_double),
                ("StopTime", ctypes.c_double),
                ("NumSamples", ctypes.c_int32),
                ("FrameNum", ctypes.c_int32),
                ]

    def __init__(self, StartTime, StopTime, FrameNum, NumSamples):
        self.StartTime=ctypes.c_double(StartTime)
        self.StopTime=ctypes.c_double(StopTime)
        self.FrameNum=ctypes.c_int32(FrameNum)
        self.NumSamples=ctypes.c_int32(NumSamples)
        
        