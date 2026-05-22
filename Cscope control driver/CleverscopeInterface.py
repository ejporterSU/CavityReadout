'''
Created on 04.11.2020
Add GetSigGenType, GetCauType, GetSerialNumber
Updated August 2021 RHC
'''

import ctypes
import os
from T_AcquireSpec import T_AcquireSpec, T_AcquireAction, T_SigGenWaveform, T_LinkPort, T_TrigChannel
from T_ChannelSpec import T_ChannelSpec, T_Probe, T_GlobalFilter, T_PreFilter20MHz, T_MA_Filter, T_ExpFilter, T_FilterOption, T_Coupling
from T_InterfaceSpec import T_InterfaceSpec, T_Interface
from T_ReplaySpec import T_ReplaySpec
from T_T0dt import T_T0dt
from CleverscopeClasses import T_CAUStatus, T_Command, T_FunctionCommand, T_LinkMasterSlave, T_TriggeringUnit
from time import sleep, time

class Cleverscope:
	def __init__( self, 
			  UnitNumber, InterfaceSource, IPAddr, TCP_Port, SerialNumber,
			  StartTime, StopTime, FrameNum, NumSamples, MaximumSamples,
			  TriggerSource, TriggerLevel, LinkPort,
			  ProbeMinVoltage, ProbeMaxVoltage, ProbeAGain, ProbeBGain, ProbeCGain, ProbeDGain, ProbeCoupling
		):

		self.AcquisitionUnit = ctypes.c_int32(UnitNumber)

		#Initialise Interface Spec
		self.InterfaceSpec = T_InterfaceSpec(InterfaceSource, IPAddr,TCP_Port, SerialNumber)

		#Initialise Acquire Spec
		self.AcquireSpec = T_AcquireSpec(StartTime, StopTime, LinkPort, TriggerSource, TriggerLevel)

		#Initialise Replay Spec
		self.ReplaySpec = T_ReplaySpec(StartTime, StopTime, FrameNum, NumSamples)

		#Initialise Channel Spec
		self.MaxChannels = 4
		self.T_ChannelSpecArray = T_ChannelSpec * self.MaxChannels
		self.ChannelSpecArray = self.T_ChannelSpecArray()
		self.NumberOfChannels = ctypes.c_int32(self.MaxChannels)
		for i in range(self.MaxChannels):
			if i==1:
				self.ChannelSpecArray[i].Init(ProbeMinVoltage, ProbeMaxVoltage, ProbeAGain, ProbeCoupling)
			elif i==2:
				self.ChannelSpecArray[i].Init(ProbeMinVoltage, ProbeMaxVoltage, ProbeBGain, ProbeCoupling)
			elif i==3:
				self.ChannelSpecArray[i].Init(ProbeMinVoltage, ProbeMaxVoltage, ProbeCGain, ProbeCoupling)
			else:
				self.ChannelSpecArray[i].Init(ProbeMinVoltage, ProbeMaxVoltage, ProbeDGain, ProbeCoupling)
		
		#Create Function Call Link Data Buffers (Rx and Tx)
		self.LinkDataBufferSize = 50
		self.T_LinkDataBuffer = ctypes.c_uint8 * self.LinkDataBufferSize
		self.LinkDataBufferOut = self.T_LinkDataBuffer()
		self.LinkDataBufferIn = self.T_LinkDataBuffer()
		self.FunctionResult = ctypes.c_double(0)
		self.FunctionResultA = ctypes.c_double(0)
		self.FunctionResultB = ctypes.c_double(0)
		self.FunctionResultC = ctypes.c_double(0)
		self.FunctionResultD = ctypes.c_double(0)


		#Create Channel Sample Arrays (4 Channels A to D)
		self.MaxSamples = MaximumSamples
		self.T_AnalogChannelSamples = ctypes.c_float * self.MaxSamples
		self.T_DigitalChannelSamples = ctypes.c_uint16 * self.MaxSamples
		self.ChannelAData = self.T_AnalogChannelSamples()
		self.ChannelBData = self.T_AnalogChannelSamples()
		self.ChannelCData = self.T_AnalogChannelSamples()
		self.ChannelDData = self.T_AnalogChannelSamples()
		self.DigitalData = self.T_DigitalChannelSamples()
		self.SampleBufferSize = ctypes.c_int32 (self.MaxSamples)

		#Create Get Hardware Info Array Types
		# Serial number array setup
		self.SerialNumberArraySize = 8
		self.T_SerialNumberArray = ctypes.c_byte * self.SerialNumberArraySize
		# CAU Type array setup
		self.CAUTypeArraySize = 16
		self.T_CAUTypeArray = ctypes.c_byte * self.CAUTypeArraySize
		# Sig Gen Type array setup
		self.SigGenTypeArraySize = 16
		self.T_SigGenTypeArray = ctypes.c_byte * self.SigGenTypeArraySize
		# IP Address Type array setup
		self.IPAddressArraySize = 128
		self.T_IPAddressArray = ctypes.c_byte * self.IPAddressArraySize


		#Init Driver Call Values
		self.GotSamples = ctypes.c_bool(0)
		self.CscopeStatus = T_CAUStatus() #ctypes.c_uint16(0)
		self.T0dt = T_T0dt()
	
		######################
		### DLL PROTOTYPES ###
		######################

		_dll_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Cscope control driver 64.dll")
		self.CscopeDLL = ctypes.WinDLL(_dll_path)

		###### NOTES:
		# For the self.xxxxxxParams below, the values such as = (1,"p1",0) or (A, B, C) have the following meanings:
		# A) An integer containing a combination of direction flags for the parameter
		#		1 = Specifies an input parameter to the function.
		#		2 = Output parameter. The foreign function fills in a value.
		#		4 = Input parameter which defaults to the integer zero.
		# B) [Optional] A string name for the parameter
		# C) [Optional] Default value for the parameter


		#### CALL CSCOPE CONTROL DRIVER ####
		self.CallCscopeControlDriver = self.CscopeDLL.CscopeControlDriver
		self.CallCscopeControlDriver.restype = ctypes.c_int
		self.CallCscopeControlDriver.argtypes = \
			[
			ctypes.c_int32,						#Param 1  # AcquisitionUnit,
			ctypes.c_uint16,					#Param 2  # Command,
			ctypes.POINTER(T_AcquireSpec),						#Param 3  # *AcquireSpec,
			ctypes.POINTER(T_ReplaySpec),						#Param 4  # *ReplaySpec,
			ctypes.POINTER(T_InterfaceSpec),					#Param 5  # *InterfaceSpec,
			ctypes.POINTER(self.T_ChannelSpecArray),			#Param 6  # ChannelSpec[],
			ctypes.c_int32,						#Param 7  # ChannelSpecLength,
			ctypes.POINTER(ctypes.c_bool),		#Param 8  # *GotSamples,
			ctypes.POINTER(ctypes.c_uint16),	#Param 9  # *CAUStatus,
			ctypes.POINTER(self.T_AnalogChannelSamples),		#Param 10 # ChanA[],
			ctypes.POINTER(self.T_AnalogChannelSamples),		#Param 11 # ChanB[],
			ctypes.POINTER(self.T_AnalogChannelSamples),		#Param 12 # ChanC[],
			ctypes.POINTER(self.T_AnalogChannelSamples),		#Param 13 # ChanD[],
			ctypes.POINTER(self.T_DigitalChannelSamples),	#Param 14 # DigitalData[],
			ctypes.c_int32,						#Param 15 # SampleBufferSize,
			ctypes.POINTER(T_T0dt)				#Param 16 # *T0dt
			]

		#### CALL CSCOPE FUNCTION ####
		self.CallCscopeFunction = self.CscopeDLL.CscopeFunction
		self.CallCscopeFunction.restype = ctypes.c_int
		self.CallCscopeFunction.argtypes = \
			[
			ctypes.c_int32,										#Param 1  # AcquisitionUnit
			ctypes.c_uint16,									#Param 2  # T_FunctionCommand
			ctypes.c_double,									#Param 3  # Parameter
			ctypes.POINTER(self.T_LinkDataBuffer),				#Param 4  # *LinkDataSend
			ctypes.c_int32,										#Param 5  # LengthOfLinkDataSend
			ctypes.POINTER(ctypes.c_double),					#Param 6  # *FunctionResult
			ctypes.POINTER(self.T_LinkDataBuffer),				#Param 7  # *LinkDataReceived
			ctypes.c_int32,										#Param 8  # LengthOfLinkDataReceived
			ctypes.POINTER(ctypes.c_double),					#Param 9  # *ResultA
			ctypes.POINTER(ctypes.c_double),					#Param 10 # *ResultB
			ctypes.POINTER(ctypes.c_double),					#Param 11 # *ResultC
			ctypes.POINTER(ctypes.c_double)						#Param 12 # *ResultD
			]

		#### CALL CSCOPE GET HARDWARE INFORMATION ####
		self.CallCscopeGetHardwareInformation = self.CscopeDLL.CscopeGetHardwareInformation
		self.CallCscopeGetHardwareInformation.restype = ctypes.c_int
		self.CallCscopeGetHardwareInformation.argtypes = \
			[
			ctypes.c_int32,										#Param 1  # AcquisitionUnit,
			ctypes.POINTER(self.T_SerialNumberArray),			#Param 2  # SerialNumber[],
			ctypes.c_int32,										#Param 3  # SerialNumberLength,
			ctypes.POINTER(self.T_CAUTypeArray),				#Param 4  # CAUType[],
			ctypes.c_int32,										#Param 5  # CAUTypeLength,
			ctypes.POINTER(ctypes.c_int32),						#Param 6  # *NumChannels,
			ctypes.POINTER(ctypes.c_int32),						#Param 7  # *ADCResolution,
			ctypes.POINTER(self.T_SigGenTypeArray),				#Param 8  # SigGenType[],
			ctypes.c_int32,										#Param 9  # SigGenTypeLength,
			ctypes.POINTER(self.T_IPAddressArray),				#Param 10 # IPAddress[],
			ctypes.c_int32,										#Param 11 # IPAddressLength,
			ctypes.POINTER(ctypes.c_int32)						#Param 12 # *TCPPort
			]


		
	def DoCscopeFunction(self, Function,Parameter):
		self.CallCscopeFunction(self.AcquisitionUnit,
                                Function,
                                Parameter,
                                ctypes.byref(self.LinkDataBufferOut),
                                self.LinkDataBufferSize,
                                ctypes.byref(self.FunctionResult),
                                ctypes.byref(self.LinkDataBufferIn),
                                self.LinkDataBufferSize,
                                ctypes.byref(self.FunctionResultA),
                                ctypes.byref(self.FunctionResultB),
                                ctypes.byref(self.FunctionResultC),
                                ctypes.byref(self.FunctionResultD)
                                )
		return self.FunctionResult

	def GetCscopeStatus(self):
		Status = ctypes.c_uint16(0)
		self.CscopeDLL.CscopeGetStatus(self.AcquisitionUnit, ctypes.byref(Status))
		self.CscopeStatus = Status
		return self.CscopeStatus

	def GetNumberOfChannels(self):
		NumberOfChannels = ctypes.c_int32(0)
		ADCResolution = ctypes.c_int32(0)
		TCPPort = ctypes.c_int32(0)
		# Serial number array setup
		SerialNumberArray = self.T_SerialNumberArray()
		# CAU Type array setup
		CAUTypeArray = self.T_CAUTypeArray()
		# Sig Gen Type array setup
		SigGenTypeArray = self.T_SigGenTypeArray()
		# IP Address Type array setup
		IPAddressArray = self.T_IPAddressArray()

		self.CallCscopeGetHardwareInformation(	self.AcquisitionUnit,						#Param 1  # AcquisitionUnit,
												ctypes.byref(SerialNumberArray),			#Param 2  # SerialNumber[],
												ctypes.c_int32(self.SerialNumberArraySize),#Param 3  # SerialNumberLength,
												ctypes.byref(CAUTypeArray),					#Param 4  # CAUType[],
												ctypes.c_int32(self.CAUTypeArraySize),		#Param 5  # CAUTypeLength,
												ctypes.byref(NumberOfChannels),				#Param 6  # *NumChannels,
												ctypes.byref(ADCResolution),				#Param 7  # *ADCResolution,
												ctypes.byref(SigGenTypeArray),				#Param 8  # SigGenType[],
												ctypes.c_int32(self.SigGenTypeArraySize),	#Param 9  # SigGenTypeLength,
												ctypes.byref(IPAddressArray),				#Param 10  # IPAddress[],
												ctypes.c_int32(self.IPAddressArraySize),	#Param 11  # IPAddressLength,
												ctypes.byref(TCPPort)						#Param 12  # *TCPPort
												)
		return NumberOfChannels.value
	
	
	def GetSigGenType(self):
		NumberOfChannels = ctypes.c_int32(0)
		ADCResolution = ctypes.c_int32(0)
		TCPPort = ctypes.c_int32(0)
		# Serial number array setup
		SerialNumberArray = self.T_SerialNumberArray()
		# CAU Type array setup
		CAUTypeArray = self.T_CAUTypeArray()
		# Sig Gen Type array setup
		SigGenTypeArray = self.T_SigGenTypeArray()
		# IP Address Type array setup
		IPAddressArray = self.T_IPAddressArray()

		self.CallCscopeGetHardwareInformation(	self.AcquisitionUnit,						#Param 1  # AcquisitionUnit,
												ctypes.byref(SerialNumberArray),			#Param 2  # SerialNumber[],
												ctypes.c_int32(self.SerialNumberArraySize),#Param 3  # SerialNumberLength,
												ctypes.byref(CAUTypeArray),					#Param 4  # CAUType[],
												ctypes.c_int32(self.CAUTypeArraySize),		#Param 5  # CAUTypeLength,
												ctypes.byref(NumberOfChannels),				#Param 6  # *NumChannels,
												ctypes.byref(ADCResolution),				#Param 7  # *ADCResolution,
												ctypes.byref(SigGenTypeArray),				#Param 8  # SigGenType[],
												ctypes.c_int32(self.SigGenTypeArraySize),	#Param 9  # SigGenTypeLength,
												ctypes.byref(IPAddressArray),				#Param 10  # IPAddress[],
												ctypes.c_int32(self.IPAddressArraySize),	#Param 11  # IPAddressLength,
												ctypes.byref(TCPPort)						#Param 12  # *TCPPort
												)
		SigGenString = "".join(map(chr, SigGenTypeArray))
		return SigGenString

	def GetCAUType(self):
		NumberOfChannels = ctypes.c_int32(0)
		ADCResolution = ctypes.c_int32(0)
		TCPPort = ctypes.c_int32(0)
		# Serial number array setup
		SerialNumberArray = self.T_SerialNumberArray()
		# CAU Type array setup
		CAUTypeArray = self.T_CAUTypeArray()
		# Sig Gen Type array setup
		SigGenTypeArray = self.T_SigGenTypeArray()
		# IP Address Type array setup
		IPAddressArray = self.T_IPAddressArray()

		self.CallCscopeGetHardwareInformation(	self.AcquisitionUnit,						#Param 1  # AcquisitionUnit,
												ctypes.byref(SerialNumberArray),			#Param 2  # SerialNumber[],
												ctypes.c_int32(self.SerialNumberArraySize), #Param 3  # SerialNumberLength,
												ctypes.byref(CAUTypeArray),					#Param 4  # CAUType[],
												ctypes.c_int32(self.CAUTypeArraySize),		#Param 5  # CAUTypeLength,
												ctypes.byref(NumberOfChannels),				#Param 6  # *NumChannels,
												ctypes.byref(ADCResolution),				#Param 7  # *ADCResolution,
												ctypes.byref(SigGenTypeArray),				#Param 8  # SigGenType[],
												ctypes.c_int32(self.SigGenTypeArraySize),	#Param 9  # SigGenTypeLength,
												ctypes.byref(IPAddressArray),				#Param 10  # IPAddress[],
												ctypes.c_int32(self.IPAddressArraySize),	#Param 11  # IPAddressLength,
												ctypes.byref(TCPPort)						#Param 12  # *TCPPort
												)
		CAUTypeString = "".join(map(chr, CAUTypeArray))
		return CAUTypeString


	def GetSerialNumber(self):
		NumberOfChannels = ctypes.c_int32(0)
		ADCResolution = ctypes.c_int32(0)
		TCPPort = ctypes.c_int32(0)
		# Serial number array setup
		SerialNumberArray = self.T_SerialNumberArray()
		# CAU Type array setup
		CAUTypeArray = self.T_CAUTypeArray()
		# Sig Gen Type array setup
		SigGenTypeArray = self.T_SigGenTypeArray()
		# IP Address Type array setup
		IPAddressArray = self.T_IPAddressArray()

		self.CallCscopeGetHardwareInformation(	self.AcquisitionUnit,						#Param 1  # AcquisitionUnit,
												ctypes.byref(SerialNumberArray),			#Param 2  # SerialNumber[],
												ctypes.c_int32(self.SerialNumberArraySize),#Param 3  # SerialNumberLength,
												ctypes.byref(CAUTypeArray),					#Param 4  # CAUType[],
												ctypes.c_int32(self.CAUTypeArraySize),		#Param 5  # CAUTypeLength,
												ctypes.byref(NumberOfChannels),				#Param 6  # *NumChannels,
												ctypes.byref(ADCResolution),				#Param 7  # *ADCResolution,
												ctypes.byref(SigGenTypeArray),				#Param 8  # SigGenType[],
												ctypes.c_int32(self.SigGenTypeArraySize),	#Param 9  # SigGenTypeLength,
												ctypes.byref(IPAddressArray),				#Param 10  # IPAddress[],
												ctypes.c_int32(self.IPAddressArraySize),	#Param 11  # IPAddressLength,
												ctypes.byref(TCPPort)						#Param 12  # *TCPPort
												)
		SerialNumberString = "".join(map(chr, SerialNumberArray))
		return SerialNumberString

	def GetIPAddress(self):
		NumberOfChannels = ctypes.c_int32(0)
		ADCResolution = ctypes.c_int32(0)
		TCPPort = ctypes.c_int32(0)
		# Serial number array setup
		SerialNumberArray = self.T_SerialNumberArray()
		# CAU Type array setup
		CAUTypeArray = self.T_CAUTypeArray()
		# Sig Gen Type array setup
		SigGenTypeArray = self.T_SigGenTypeArray()
		# IP Address Type array setup
		IPAddressArray = self.T_IPAddressArray()

		self.CallCscopeGetHardwareInformation(	self.AcquisitionUnit,						#Param 1  # AcquisitionUnit,
												ctypes.byref(SerialNumberArray),			#Param 2  # SerialNumber[],
												ctypes.c_int32(self.SerialNumberArraySize),#Param 3  # SerialNumberLength,
												ctypes.byref(CAUTypeArray),					#Param 4  # CAUType[],
												ctypes.c_int32(self.CAUTypeArraySize),		#Param 5  # CAUTypeLength,
												ctypes.byref(NumberOfChannels),				#Param 6  # *NumChannels,
												ctypes.byref(ADCResolution),				#Param 7  # *ADCResolution,
												ctypes.byref(SigGenTypeArray),				#Param 8  # SigGenType[],
												ctypes.c_int32(self.SigGenTypeArraySize),	#Param 9  # SigGenTypeLength,
												ctypes.byref(IPAddressArray),				#Param 10  # IPAddress[],
												ctypes.c_int32(self.IPAddressArraySize),	#Param 11  # IPAddressLength,
												ctypes.byref(TCPPort)						#Param 12  # *TCPPort
												)
		IPAddress = "".join(map(chr, IPAddressArray))
		return IPAddress


	def SendCleverscopeCommand(self,Command):
		Status = ctypes.c_uint16(0)
		self.CallCscopeControlDriver(
			self.AcquisitionUnit,					#Param 1  # AcquisitionUnit,
			Command,								#Param 2  # Command,
			ctypes.byref(self.AcquireSpec),			#Param 3  # *AcquireSpec,
			ctypes.byref(self.ReplaySpec),			#Param 4  # *ReplaySpec,
			ctypes.byref(self.InterfaceSpec),		#Param 5  # *InterfaceSpec,
			ctypes.byref(self.ChannelSpecArray),	#Param 6  # ChannelSpec[],
			self.MaxChannels,						#Param 7  # ChannelSpecLength,
			ctypes.byref(self.GotSamples),			#Param 8  # *GotSamples,
			ctypes.byref(Status),					#Param 9  # *CAUStatus,
			ctypes.byref(self.ChannelAData),		#Param 10 # ChanA[],
			ctypes.byref(self.ChannelBData),		#Param 11 # ChanB[],
			ctypes.byref(self.ChannelCData),		#Param 12 # ChanC[],
			ctypes.byref(self.ChannelDData),		#Param 13 # ChanD[],
			ctypes.byref(self.DigitalData),			#Param 14 # DigitalData[],
			self.SampleBufferSize,					#Param 15 # SampleBufferSize,
			ctypes.byref(self.T0dt)					#Param 16 # *T0dt
			)
		self.CscopeStatus = Status
		return self.CscopeStatus

	def UpdateCleverscope(self):
		self.SendCleverscopeCommand(T_Command.T_Command_Update)
		return self.CscopeStatus

	def IsConnected(self):
		if self.CscopeStatus.value == T_CAUStatus.T_CAUStatus_Open.value:
			return True
		else:
			return False

	def ConnectToHardware(self):
		self.SendCleverscopeCommand(T_Command.T_Command_Initialize)
		return self.CscopeStatus

	def StopCapture(self):
		self.AcquireSpec.AcquireAction = T_AcquireAction.T_AcquireAction_Stop
		self.SendCleverscopeCommand(T_Command.T_Command_Update)
		return self.CscopeStatus

	def BeginSampleCapture(self, AcquireAction):
		self.AcquireSpec.AcquireAction=AcquireAction
		self.SendCleverscopeCommand(T_Command.T_Command_Acquire)
		return self.CscopeStatus

	def CheckForSampleCaptureComplete(self):
		self.SendCleverscopeCommand(T_Command.T_Command_WaitForSamples)
		return self.GotSamples

	def WaitForConnectionToComplete(self,timeout):
		check_period = 0.1 # 100ms
		intervals = int(timeout // check_period)
		#Wait for status to show connection is open
		for i in range(intervals):
			self.GetCscopeStatus() # Ask the hardware for it's connection status
			if self.IsConnected():
				break	# If connected, then break out of this loop.
			else:
				sleep(check_period) # Still not connected. Wait, and check again
		return self.CscopeStatus

	def SetDualScopelink(self, MasterSlave, TriggerSource):
		if MasterSlave.value == T_LinkMasterSlave.T_LinkMasterSlave_Master.value:
			# Set As Master
			self.AcquireSpec.LinkPort = T_LinkPort.T_LinkPort_Master
			self.AcquireSpec.TriggerSource = TriggerSource
		else:
			if MasterSlave.value == T_LinkMasterSlave.T_LinkMasterSlave_Slave.value:
				# Set As Slave
				self.AcquireSpec.LinkPort = T_LinkPort.T_LinkPort_Slave
				self.AcquireSpec.TriggerSource = T_TrigChannel.T_TrigChan_LinkInput
			else: # Disable the link port (set as debug is a common default)
				self.AcquireSpec.LinkPort = T_LinkPort.T_LinkPort_Debug
				self.AcquireSpec.TriggerSource = TriggerSource
	
	def SetupSignalGenerator(self, Frequency, Amplitude, Duty, Waveform):
		self.AcquireSpec.SigGenFreq = ctypes.c_double(Frequency)		#Frequency in Hz
		self.AcquireSpec.SigGenAmp = ctypes.c_double(Amplitude)			#Ampltude in volts
		self.AcquireSpec.SigGenDuty = ctypes.c_double(Duty)				#0..100
		self.AcquireSpec.SigGenWaveform = Waveform		#T_SigGenWaveform (T_SigGenWaveform.T_SigGenWaveform_sine for example)
		self.UpdateCleverscope()
