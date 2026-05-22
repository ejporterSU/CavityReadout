'''
Created on 04.11.2020

@author: mattkatz
'''
import ctypes



class T_Probe:
    T_Probe_x1 = ctypes.c_uint16(0)
    T_Probe_x10 = ctypes.c_uint16(1)
    T_Probe_x100 = ctypes.c_uint16(2)
    T_Probe_x1K = ctypes.c_uint16(3)
    T_Probe_x2 = ctypes.c_uint16(4)
    T_Probe_x20 = ctypes.c_uint16(5)
    T_Probe_x50 = ctypes.c_uint16(6)
    T_Probe_x200 = ctypes.c_uint16(7)
    T_Probe_Vsat_0_15 = ctypes.c_uint16(8)
    T_Probe_Vsat_1_50 = ctypes.c_uint16(9)
    T_Probe_Vsat_15_0 = ctypes.c_uint16(10)
    T_Probe_Vsat_x2 = ctypes.c_uint16(11)


class T_Coupling:
    T_Coupling_AC = ctypes.c_uint16(0)
    T_Coupling_DC = ctypes.c_uint16(1)


class T_FilterOption:
    T_FilterOption_NoFilter = ctypes.c_uint16(0)
    T_FilterOption__4xMA_2xExp = ctypes.c_uint16(1)
    T_FilterOption__8xMA_4xExp = ctypes.c_uint16(2)
    T_FilterOption__16xMA_8xExp = ctypes.c_uint16(3)
    T_FilterOption__32xMA_16xExp = ctypes.c_uint16(4)
    T_FilterOption__64xMA_32xExp = ctypes.c_uint16(5)
    T_FilterOption__2048xMA_64xExp = ctypes.c_uint16(6)
    T_FilterOption_XXXxMA_2048xExp = ctypes.c_uint16(7)
    
class T_GlobalFilter:
    T_GlobalFilter_Off=ctypes.c_uint8(0)
    T_GlobalFilter_On=ctypes.c_uint8(1)

class T_PreFilter20MHz:
    T_PreFilter20MHz_Off=ctypes.c_uint8(0)
    T_PreFilter20MHz_On=ctypes.c_uint8(1)
    
class T_MA_Filter:
    T_MA_Filter_Off=ctypes.c_uint8(0)
    T_MA_Filter_On=ctypes.c_uint8(1)

class T_ExpFilter:
    T_ExpFilter_Off=ctypes.c_uint8(0)
    T_ExpFilter_On=ctypes.c_uint8(1)

class T_ChannelSpec(ctypes.Structure):
    _fields_ = [("Max", ctypes.c_double),
                ("Min", ctypes.c_double),
                ("Probe", ctypes.c_uint16),
                ("Coupling", ctypes.c_uint16),
                ("GlobalFilter", ctypes.c_uint8),
                ("PreFilter20MHz", ctypes.c_uint8),
                ("MA_Filter", ctypes.c_uint8),
                ("Exp_Filter", ctypes.c_uint8),
                ("T_FilterOption", ctypes.c_uint16),
                ]
    
    def Init(self, ProbeMinVoltage, ProbeMaxVoltage, ProbeGain, ProbeCoupling):
        self.Max=ctypes.c_double(ProbeMaxVoltage)
        self.Min=ctypes.c_double(ProbeMinVoltage)
        self.Coupling=ProbeCoupling
        self.Probe=ProbeGain
        self.GlobalFilter=ctypes.c_uint8(0) #Global Filter Off
        self.PreFukter20MHz=ctypes.c_uint8(0) #20MHz filter Off
        self.MA_Filter=ctypes.c_uint8(0) #No Moving Average Filtering
        self.Exp_Filter=ctypes.c_uint8(0) #No Exponential Filtering
        self.FilterOption=ctypes.c_uint8(0) #No Exponential Filtering'''
