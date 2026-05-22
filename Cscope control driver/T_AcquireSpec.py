'''
Created on 04.11.2020

@author: mattkatz
'''
import ctypes

class T_AcquireAction:
    T_AcquireAction_Single = ctypes.c_uint16(0)
    T_AcquireAction_Automatic = ctypes.c_uint16(1)
    T_AcquireAction_Triggered = ctypes.c_uint16(2)
    T_AcquireAction_Stop = ctypes.c_uint16(3)
    T_AcquireAction_SingleStop = ctypes.c_uint16(4)
    T_AcquireAction_Replay = ctypes.c_uint16(5)
    T_AcquireAction_Chart = ctypes.c_uint16(6)

class T_AcquireMode:
    T_AcquireMode_Sampled = ctypes.c_uint16(0)
    T_AcquireMode_PeakCaptured = ctypes.c_uint16(1)
    T_AcquireMode_Filtered = ctypes.c_uint16(2)
    T_AcquireMode_Repetitive = ctypes.c_uint16(3)
    T_AcquireMode_WaveformAvg = ctypes.c_uint16(4)
    
class T_Acquirer:
    T_Acquirer_InternalSigGen = ctypes.c_uint16(0)
    T_Acquirer_APC901 = ctypes.c_uint16(1)
    T_Acquirer_APC901A = ctypes.c_uint16(2)
    T_Acquirer_SoundCard = ctypes.c_uint16(3)
    T_Acquirer_Cleverscope = ctypes.c_uint16(4)

class T_TransferChans:
    T_TransferChans_ChanA = ctypes.c_uint16(0)
    T_TransferChans_ChanB = ctypes.c_uint16(1)
    T_TransferChans_ChanAB = ctypes.c_uint16(2)

class T_TrigChannel:
    T_TrigChan_ChanA = ctypes.c_uint32(0)
    T_TrigChan_ChanB = ctypes.c_uint32(1)
    T_TrigChan_ExtTrigger = ctypes.c_uint32(2)
    T_TrigChan_DigTrig = ctypes.c_uint32(3)
    T_TrigChan_LinkInput = ctypes.c_uint32(4)
    T_TrigChan_ChanC = ctypes.c_uint32(5)
    T_TrigChan_ChanD = ctypes.c_uint32(6)
    T_TrigChan_ChanE = ctypes.c_uint32(7)
    T_TrigChan_ChanF = ctypes.c_uint32(8)
    T_TrigChan_ChanG = ctypes.c_uint32(9)
    T_TrigChan_ChanH = ctypes.c_uint32(10)
    T_TrigChan_ChanI = ctypes.c_uint32(11)
    T_TrigChan_ChanJ = ctypes.c_uint32(12)
    T_TrigChan_ChanK = ctypes.c_uint32(13)
    T_TrigChan_ChanL = ctypes.c_uint32(14)
    T_TrigChan_Dig2 = ctypes.c_uint32(15)

class T_TriggerFilter:
    T_TriggerFilter_None = ctypes.c_uint16(0)
    T_TriggerFilter_LowPass = ctypes.c_uint16(1)
    T_TriggerFilter_HiPass = ctypes.c_uint16(2)
    T_TriggerFilter_Noise = ctypes.c_uint16(3)

class T_TrigSlope:
    T_TrigSlope_Rising=ctypes.c_uint8(0)
    T_TrigSlope_Falling=ctypes.c_uint8(1)
    
class T_SigGenWaveform:
    T_SigGenWaveform_sine = ctypes.c_uint16(0)
    T_SigGenWaveform_triangle = ctypes.c_uint16(1)
    T_SigGenWaveform_square = ctypes.c_uint16(2)
    T_SigGenWaveform_DC = ctypes.c_uint16(3)
    T_SigGenWaveform_OFF = ctypes.c_uint16(4)

class T_DigPatternRqd:
    DigPatternRqd_NotRequired=ctypes.c_uint8(0)
    DigPatternRqd_Required=ctypes.c_uint8(1)

#See 'Cscope Control Driver DLL description.pdf' for options
class T_DigPattern:
    T_DigPattern_Standard=ctypes.c_uint32(0)
     
class T_SigGenSweep:
    T_SigGenSweep_Linear = ctypes.c_uint16(0)
    T_SigGenSweep_Log = ctypes.c_uint16(1)


class T_SigGenFunc:
    T_SigGenFunc_Standard = ctypes.c_uint16(0)
    T_SigGenFunc_AutoAdvance = ctypes.c_uint16(1)
    T_SigGenFunc_FreqModIn8 = ctypes.c_uint16(2)
    T_SigGenFunc_PhaseModIn8 = ctypes.c_uint16(3)


class T_Trig2Function:
    T_Trig2Function_None = ctypes.c_uint16(0)
    T_Trig2Function_Trig12Min = ctypes.c_uint16(1)
    T_Trig2Function_minT12Max = ctypes.c_uint16(2)
    T_Trig2Function_Trig12Max = ctypes.c_uint16(3)
    T_Trig2Function_CountTrig1 = ctypes.c_uint16(4)
    T_Trig2Function_CountTrig2 = ctypes.c_uint16(5)


class T_Trigger2Source:
    T_Trigger2Source_Trigger1Inverted = ctypes.c_uint16(0)
    T_Trigger2Source_Trig2Defn = ctypes.c_uint16(1)

class T_LinkPort:
    T_LinkPort_Debug = ctypes.c_uint8(0)
    T_LinkPort_LinkOut = ctypes.c_uint8(1)
    T_LinkPort_Disabled = ctypes.c_uint8(2)
    T_LinkPort_Slave = ctypes.c_uint8(3)
    T_LinkPort_Master = ctypes.c_uint8(4)
    T_LinkPort_Uart = ctypes.c_uint8(5)
    T_LinkPort_SPI = ctypes.c_uint8(6)
    T_LinkPort_I2C = ctypes.c_uint8(7)
    T_LinkPort_Digital = ctypes.c_uint8(8)
    T_LinkPort_SigGen = ctypes.c_uint8(9)

class T_ExtSampleClock:
    T_ExtSampleClock_IntClock = ctypes.c_uint8(0)
    T_ExtSampleClock_ExtClockConst = ctypes.c_uint8(1)
    T_ExtSampleClock_ExtClockVar = ctypes.c_uint8(2)


class T_SamplerResolution:
    T_SamplerResolution__8Bit = ctypes.c_uint16(0)
    T_SamplerResolution__10Bit = ctypes.c_uint16(1)
    T_SamplerResolution__12Bit = ctypes.c_uint16(2)
    T_SamplerResolution__14Bit = ctypes.c_uint16(3)
    T_SamplerResolution__16Bit = ctypes.c_uint16(4)
       
       
class T_TransferSize:
    T_TransferSize_Normal = ctypes.c_uint16(0)
    T_TransferSize__100Buffer = ctypes.c_uint16(1)
    T_TransferSize__50Buffer = ctypes.c_uint16(2)
    T_TransferSize__10Buffer = ctypes.c_uint16(3)
    T_TransferSize__5Buffer = ctypes.c_uint16(4)
    T_TransferSize__2Buffer = ctypes.c_uint16(5)
    T_TransferSize_Sequence = ctypes.c_uint16(6)


class T_AcquireSpec(ctypes.Structure):
    _fields_ = [("AcquireAction", ctypes.c_uint16),
                ("AcquireMode", ctypes.c_uint16),
                ("Acquirer", ctypes.c_uint16),
                ("StartTime", ctypes.c_double),
                ("StopTime", ctypes.c_double),
                ("TransferChans", ctypes.c_uint16),
                ("TriggerSource", ctypes.c_uint32),
                ("TriggerAmplitude", ctypes.c_double),
                ("TriggerFilter", ctypes.c_uint16),
                ("TrigSlope", ctypes.c_uint8),
                ("TriggerHoldoff", ctypes.c_double),
                ("DigPatternRqd", ctypes.c_uint8),
                ("DigPattern", ctypes.c_uint32),
                ("ExtTrigThreshold", ctypes.c_double),
                ("DigInputThreshold", ctypes.c_double),
                ("NumSeqFrames", ctypes.c_int16),
                ("NumBuffers", ctypes.c_int32),
                ("SigGenFreq", ctypes.c_double),
                ("SigGenAmp", ctypes.c_double),
                ("SigGenOffset", ctypes.c_double),
                ("SigGenWaveform", ctypes.c_uint16),
                ("SigGenSweep", ctypes.c_uint16),
                ("SigGenFunc", ctypes.c_uint16),
                ("SigGenDuty", ctypes.c_double),
                ("SigGenPhase", ctypes.c_double),
                ("SigGenFreqStep", ctypes.c_double),
                ("Trig2Function", ctypes.c_uint16),
                ("MinTriggerPeriod", ctypes.c_double),
                ("MaxTriggerPeriod", ctypes.c_double),
                ("TriggerCount", ctypes.c_uint32),
                ("Trig2Slope", ctypes.c_uint8),
                ("Trig2SourceChan", ctypes.c_uint32),
                ("Trig2Level", ctypes.c_double),
                ("DigPattern2Rqd", ctypes.c_uint8),
                ("DigPattern2", ctypes.c_uint32),
                ("Trigger2Source", ctypes.c_uint16),
                ("WaveformAverages", ctypes.c_int32),
                ("FreqSpan", ctypes.c_double),
                ("FreqRes", ctypes.c_double),
                ("Duration", ctypes.c_double),
                ("Resolution", ctypes.c_double),
                ("LinkPort", ctypes.c_uint8),
                ("ExtSampleClock", ctypes.c_uint8),
                ("SamplerResolution", ctypes.c_uint16),
                ("TransferSize", ctypes.c_uint16),
                ("FunctionNumber", ctypes.c_double),
                ("FunctionParameter", ctypes.c_double),
                ("FunctionResult", ctypes.c_double),
                ("LinkStart", ctypes.c_uint32),
                ("LinkTimebase", ctypes.c_uint32),
                ("LinkTimer", ctypes.c_uint32),
                ("LinkSetup", ctypes.c_uint32),
                ("SpareU321", ctypes.c_uint32),
                ("SpareU322", ctypes.c_uint32),
                ("SpareU323", ctypes.c_uint32),
                ("SpareU324", ctypes.c_uint32),
                ("ChartSampleRate", ctypes.c_double),
                ("SpareDBL2", ctypes.c_double),
                ("SpareDBL3", ctypes.c_double),
                ("SpareDBL4", ctypes.c_double)
                ]


    def __init__(self, StartTime, StopTime, LinkPort, TriggerSource, TriggerLevel):
        self.AcquireAction=T_AcquireAction.T_AcquireAction_Stop #Stop required for Driver Init
        self.AcquireMode=T_AcquireMode.T_AcquireMode_Sampled 
        self.Acquirer=T_Acquirer.T_Acquirer_Cleverscope #Always set to 4 for cleverscopes
        self.StartTime=ctypes.c_double(StartTime) #-5ms. Sets the start time relative to the trigger
        self.StopTime=ctypes.c_double(StopTime) #5ms. Sets the stop time relative to the trigger
        self.TransferChans=T_TransferChans.T_TransferChans_ChanAB #Always set to 2 transfers all channels
        self.TriggerSource=TriggerSource
        
        self.TriggerAmplitude=ctypes.c_double(TriggerLevel) #in Volt
        self.TriggerFilter=T_TriggerFilter.T_TriggerFilter_None #0=no filter. See 'Cscope Control Driver DLL description.pdf' for options
        self.TrigSlope=T_TrigSlope.T_TrigSlope_Rising
        self.TriggerHoldoff=ctypes.c_double(0) #Not used by driver
        self.DigPatternRqd=T_DigPatternRqd.DigPatternRqd_NotRequired
        self.DigPattern=T_DigPattern.T_DigPattern_Standard 
        self.ExtTrigThreshold=ctypes.c_double(1) #Sets the amplitude of the external trigger input, -6..+18V
        self.DigInputThreshold=ctypes.c_double(1) #Sets the amplitude of the digital input threshold, 0 .. 10V
        
        self.NumSeqFrames=ctypes.c_int16(1) #Sets the number of frames captured sequentially. Read the 'Cscope Control Driver DLL description.pdf'.
        self.NumBuffers=ctypes.c_int32(2) #Sets the number of buffers allocated for frame capture. Must be at least num waveform averages + 1.
        self.SigGenFreq=ctypes.c_double(1000) #1kHz. Set the signal generator frequency in Hz. Range is 0.003..10e6 Hz.
        self.SigGenAmp=ctypes.c_double(1) #1V. P-P Amplitude of signal generator output. Range is 0..8V
        self.SigGenOffset=ctypes.c_double(0) #0V. Offset of signal generator output. Range is �5..+5V
        self.SigGenWaveform=T_SigGenWaveform.T_SigGenWaveform_sine
        self.SigGenSweep=ctypes.c_uint16(0) #Not used by driver
        self.SigGenFunc=T_SigGenFunc.T_SigGenFunc_Standard #0 means normal sig gen use, 1 means step the sig gen upwards by Sig Gen Freq Step automatically following a trigger.
        self.SigGenDuty=ctypes.c_double(50) #0 to 100%
        self.SigGenPhase=ctypes.c_double(0) #Not used by driver
        self.SigGenFreqStep=ctypes.c_double(0) #Frequency increment used when acquisition unit automatically steps the signal generator frequency following a trigger, if Sig gen Func = 1.
        
        self.Trig2Function=T_Trig2Function.T_Trig2Function_None #0=Not used. See 'Cscope Control Driver DLL description.pdf' for options
        self.MinTriggerPeriod=ctypes.c_double(10e-9) #For Trig2. Sets the min period. 0..22 secs, resolution is 10 ns.
        self.MaxTriggerPeriod=ctypes.c_double(1) #For Trig2. Sets the max period. 0..22 secs, resolution is 10 ns.
        self.TriggerCount=ctypes.c_uint32(0) #For Trig2. Sets the number of counts for counting. 0..4,294,967,295
        self.Trig2Slope=T_TrigSlope.T_TrigSlope_Rising #For Trig2. Sets the slope for trigger 2. 0 = rising, 1 = falling
        self.Trig2SourceChan=T_TrigChannel.T_TrigChan_ChanA 
        
        self.Trig2Level=ctypes.c_double(0) #For Trig2. Sets the trigger 2 threshold level.
        self.DigPattern2Rqd=T_DigPatternRqd.DigPatternRqd_NotRequired #For Trig2. Sets if Trigger 2 is qualified by the pattern.
        self.DigPattern2=T_DigPattern.T_DigPattern_Standard #For Trig2. Defines the trigger 2 digital pattern.
        self.Trigger2Source=T_Trigger2Source.T_Trigger2Source_Trigger1Inverted #For Trig2. 0 = Trigger 1 inverted, 1= Use the Trigger 2 definition
        self.WaveformAverages=ctypes.c_int32(1) #Sets how many waveforms to average in acquisition unit if acquisition mode = waveform avg. Values are 1, 4, 16, 64 and 128
        self.FreqSpan=ctypes.c_double(0) #Not used by driver
        self.FreqRes=ctypes.c_double(0) #Not used by driver
        self.Duration=ctypes.c_double(0) #Not used by driver
        self.Resolution=ctypes.c_double(0) #Not used by driver
        self.LinkPort=LinkPort #See 'Cscope Control Driver DLL description.pdf' for options
        self.ExtSampleClock=T_ExtSampleClock.T_ExtSampleClock_IntClock #See 'Cscope Control Driver DLL description.pdf' for options
        
        self.SamplerResolution=T_SamplerResolution.T_SamplerResolution__16Bit #Sets the sampler resolution to be used, 0 = 8 bits, 1 = 10 bits, 2 = 12 bits, 3 = 14, 4 = 16. Will clip to maximum resolution available.
        self.TransferSize=T_TransferSize.T_TransferSize_Normal #Use 0 to transfer one frame. Use 6 to transfer all the frames in a sequential capture as one array
        
        self.FunctionNumber=ctypes.c_double(0) #Should not be used directly. Leave as 0.
        self.FunctionParameter=ctypes.c_double(0) #Should not be used directly. Leave as 0.
        self.FunctionResult=ctypes.c_double(0) #Should not be used directly. Leave as 0.
        
        #todo Enum
        self.LinkStart=ctypes.c_uint32(1) #See 'Cscope Control Driver DLL description.pdf' for options
        self.LinkTimebase=ctypes.c_uint32(0) #Clock used to run uart, i2C, spi, or digital outputs. In 1/70Mhz units. = 14.29ns.
        self.LinkTimer=ctypes.c_uint32(0) #timer used for repeated messages, in 10us units.
        self.LinkSetup=ctypes.c_uint32(0) #See 'Cscope Control Driver DLL description.pdf' for options
        
        self.SpareU321=ctypes.c_uint32(0) #Reserved
        self.SpareU322=ctypes.c_uint32(0) #Reserved
        self.SpareU323=ctypes.c_uint32(0) #Reserved
        self.SpareU324=ctypes.c_uint32(0) #Reserved
       
        self.ChartSampleRate=ctypes.c_double(100000) #100K samples per second for charting

        self.SpareDBL2=ctypes.c_double(0) #Reserved
        self.SpareDBL3=ctypes.c_double(0) #Reserved
        self.SpareDBL4=ctypes.c_double(0) #Reserved
            