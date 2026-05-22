'''
Created on 04.11.2020
Added two scope and eight channel capability
Shifted generic graph parameters into mpl.rcParams
Added DLL Version
Updated August 2021 RHC 
'''


import CleverscopeInterface
from T_AcquireSpec import T_AcquireSpec, T_AcquireAction, T_SigGenWaveform, T_LinkPort, T_TrigChannel
from T_ChannelSpec import T_ChannelSpec, T_Probe, T_GlobalFilter, T_PreFilter20MHz, T_MA_Filter, T_ExpFilter, T_FilterOption, T_Coupling
from T_InterfaceSpec import T_InterfaceSpec, T_Interface
from T_ReplaySpec import T_ReplaySpec
from T_T0dt import T_T0dt
from CleverscopeClasses import T_CAUStatus, T_Command, T_FunctionCommand, T_LinkMasterSlave, T_TriggeringUnit
from time import sleep, time
import ctypes

#Install these addional Packages:
import platform               
import msvcrt
import numpy as np 
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
from cycler import cycler

# Set the default color cycle to Labview colour convention
mpl.rcParams['axes.prop_cycle'] = cycler('color',['#FF0000', '#0000FF', '#037100', '#FF8000','#B34B00','#5200A4','#723636','#800000'])

#set colors for chart parameters
params = {'text.color':'white', 'xtick.color':'white', 'ytick.color':'white', 'figure.facecolor':'green', 'axes.facecolor':'0.7'} 
mpl.rcParams.update(params)                                

############ Definition of sub-routines  #########

def DrawPlot(UnitA,UnitB, DualScope, FourChannel):

	#For this plot, we assume the T0dt values are the same for both connected cleverscopes (if DualScope)
	StartTime = UnitA.T0dt.T0
	StopTime = UnitA.T0dt.T0 + (UnitA.T0dt.n * UnitA.T0dt.dt)
	
	if FourChannel:
		if DualScope:
			Channels = 'CS448 Eight'
			dfChans= pd.DataFrame(index=np.arange(start=StartTime, stop=StopTime, step=UnitA.T0dt.dt), columns=['Chan A','Chan B','Chan C','Chan D','Chan E','Chan F','Chan G','Chan H'])
		else:
			Channels = 'CS448 Four'
			dfChans= pd.DataFrame(index=np.arange(start=StartTime, stop=StopTime, step=UnitA.T0dt.dt), columns=['Chan A','Chan B','Chan C','Chan D'])
	else:
		if DualScope:
			Channels = 'CS328A Four'
			dfChans= pd.DataFrame(index=np.arange(start=StartTime, stop=StopTime, step=UnitA.T0dt.dt), columns=['Chan A','Chan B','Chan C','Chan D']) 
		else:
			Channels = 'CS328A Two'
			dfChans= pd.DataFrame(index=np.arange(start=StartTime, stop=StopTime, step=UnitA.T0dt.dt), columns=['Chan A','Chan B']) 

	if FourChannel:								# For CS448
		dfChans['Chan A']=UnitA.ChannelAData
		dfChans['Chan B']=UnitA.ChannelBData
		dfChans['Chan C']=UnitA.ChannelCData
		dfChans['Chan D']=UnitA.ChannelDData
		if DualScope:
			dfChans['Chan E']=UnitB.ChannelAData
			dfChans['Chan F']=UnitB.ChannelBData
			dfChans['Chan G']=UnitB.ChannelCData
			dfChans['Chan H']=UnitB.ChannelDData
	else:										# For CS320A/CS328A
		dfChans['Chan A']=UnitA.ChannelAData
		dfChans['Chan B']=UnitA.ChannelBData
		if DualScope:
			dfChans['Chan C']=UnitB.ChannelAData
			dfChans['Chan D']=UnitB.ChannelBData
	
	dfChans.plot()  


	plt.gcf().canvas.manager.set_window_title('Cleverscope Python Demonstration');
	plt.xlabel('Time');
	plt.ylabel('Voltage');
	plt.title(Channels + ' Channel Oscilloscope');
	plt.show()


def GetAndDisplayUnitInfo(CscopeUnit):
	FunctionsToCall = ['ID','FirmwareVer','DriverVer','Resolution','FrameLength','Temperature', ]
	for i,info in enumerate(FunctionsToCall):
		CscopeUnit.DoCscopeFunction(ctypes.c_uint16(i),0)
		if info=='DriverVer':
			print("%s: %.3f" %('DLL Version',CscopeUnit.FunctionResult.value))
		else:
			print("%s: %.0f" %(info,CscopeUnit.FunctionResult.value))

#### Used to poll keyboard to cancel sampling
def GetKeyPressed(): 
   x = msvcrt.kbhit()
   if x: 
      ret = ord(msvcrt.getch()) 
   else: 
      ret = 0 
   return ret

### Wait for Key Input with timeout option
def WaitForKey(Timeout):
	StartTime = time()
	KeyPressed = 0
	while KeyPressed == 0:
		sleep(0.010) #sleep 10ms
		KeyPressed = GetKeyPressed()
		#if KeyPressed != 0:
		#	print(KeyPressed)
		if (Timeout>0) and (time()-StartTime >Timeout):
			break
	return KeyPressed

### Print the T0dt to the display
def	PrintT0dt(Label, CscopeUnit):
	print(Label)
	print("  T0dt.dt: ",CscopeUnit.T0dt.dt)
	print("  T0dt.n: ",CscopeUnit.T0dt.n)
	print("  T0dt.T0: ",CscopeUnit.T0dt.T0)
	print("  T0dt.TTrig: ",CscopeUnit.T0dt.TTrig)
	print("  T0dt.Frame: ",CscopeUnit.T0dt.Frame)

### Get DC Average of samples
def CalculateSampleAverage(Samples):
	Average=sum(Samples)/len(Samples)
	return Average

### Get Peak to Peak Amplitide of waveform
def CalculateAmplitude(Samples):
	Amplitude=max(Samples)-min(Samples)
	return Amplitude


################# End of Sub-routines




###########  Set triggering Parameters
TriggeringUnit = T_TriggeringUnit.T_TriggeringUnit_UnitA # Trigger on Unit A (used when LinkedDualScope is True)
UnitATriggerChannel = T_TrigChannel.T_TrigChan_ChanA	 # Unit A will Trigger on Channel A (if LinkedDualScope then the Triggering Unit will impact on this setting)
UnitBTriggerChannel = T_TrigChannel.T_TrigChan_ChanA     # Unit B will Trigger on Channel A (if LinkedDualScope then the Triggering Unit will impact on this setting)
AcquisitionTypeToDo = T_AcquireAction.T_AcquireAction_Automatic #Choose Single, Automatic, or Triggered


#################  Main Code ########################
print("###### CLEVERSCOPE EXAMPLE ######\n")
AcquisitionUnitA = 0
AcquisitionUnitB = 1


########### Ask the user to select either single scope, or Dual Scope
DualScope = False
LinkedDualScope = False
FourChannel = False
Debug = False                                             

print("Dual Scope? Y/N: ")
KeyPressed = WaitForKey(5) # wait for 5 seconds
if KeyPressed==121 or KeyPressed==89: #ord 121 == y ord 89 == Y
	DualScope = True
	print("DUAL SCOPE ACTIVE")
	print("Are the two units connected by a link cable? Y/N: ")
	KeyPressed = WaitForKey(5)
	if KeyPressed==121 or KeyPressed==89: #ord 121 == y ord 89 == Y
		LinkedDualScope = True
		print("DUAL LINKED SCOPES")
	else:
		print("DUAL SEPERATE (unlinked) SCOPES")
else:
	print("SINGLE SCOPE")

print("Debug Mode? Y/N: ")
KeyPressed = WaitForKey(5) # wait for 5 seconds
if KeyPressed==121 or KeyPressed==89: #ord 121 == y ord 89 == Y
	Debug = True
	print("Debug Active")
else: 
	print("Debug NOT Active")
print("___________________")
print("# Initialising... #\n")


# Set some Parameters
StartTime = -0.005
StopTime = 0.005
ProbeMinVoltage = -3
ProbeMaxVoltage = 3
Numsamples = 10000
MaximumSamples = 10000
FrameNum = 0

# SCOPE UNIT A
CscopeUnitA = CleverscopeInterface.Cleverscope(AcquisitionUnitA,
											   InterfaceSource = T_Interface.T_Interface_EthernetOrUSBFirstFound,
											   IPAddr = '10.1.5.45',
											   TCP_Port = 53270, 
											   SerialNumber='IT10081',
											   StartTime = StartTime,
											   StopTime =StopTime,  
											   FrameNum = FrameNum, 
											   NumSamples = Numsamples,
											   MaximumSamples = MaximumSamples,
											   TriggerSource = UnitATriggerChannel, 
											   TriggerLevel = .5, 
											   LinkPort = T_LinkPort.T_LinkPort_Debug,
											   ProbeMinVoltage = ProbeMinVoltage,
											   ProbeMaxVoltage = ProbeMaxVoltage, 
											   ProbeAGain = T_Probe.T_Probe_Vsat_x2,
											   ProbeBGain = T_Probe.T_Probe_x10,
											   ProbeCGain = T_Probe.T_Probe_x1,
											   ProbeDGain = T_Probe.T_Probe_x1,
											   ProbeCoupling = T_Coupling.T_Coupling_DC)

if DualScope:
	# SCOPE UNIT B
	CscopeUnitB = CleverscopeInterface.Cleverscope(AcquisitionUnitB,
											   InterfaceSource = T_Interface.T_Interface_EthernetOrUSBFirstFound,
											   IPAddr = '192.168.1.102',
											   TCP_Port = 53270, 
											   SerialNumber='IT10082',
											   StartTime = StartTime, 
											   StopTime = StopTime,    
											   FrameNum = FrameNum, 
											   NumSamples = Numsamples,
											   MaximumSamples = MaximumSamples,
											   TriggerSource = UnitBTriggerChannel, 
											   TriggerLevel = .5, 
											   LinkPort = T_LinkPort.T_LinkPort_Debug,
											   ProbeMinVoltage = ProbeMinVoltage,
											   ProbeMaxVoltage = ProbeMaxVoltage, 
											   ProbeAGain = T_Probe.T_Probe_x1, 
											   ProbeBGain = T_Probe.T_Probe_x1, 
											   ProbeCGain = T_Probe.T_Probe_x1, 
											   ProbeDGain = T_Probe.T_Probe_x1, 
											   ProbeCoupling = T_Coupling.T_Coupling_DC)

else:
	CscopeUnitB = 0


########### Connect to the Hardware for each of the scopes
CscopeUnitA.ConnectToHardware()
if DualScope:
	CscopeUnitB.ConnectToHardware()

	### Advise Versions  ####
print('Python Version:  ',platform.python_version())

########### Wait for each unit to complete their connection
# SCOPE UNIT A
CscopeUnitA.WaitForConnectionToComplete(5)
if CscopeUnitA.IsConnected():
	if Debug:
		CscopeUnitA.DoCscopeFunction(9999,0)
	print("______________________________")  # Provide some details of Unit A
	print("Hardware (Unit A) connected OK")
	SerialNumber = CscopeUnitA.GetSerialNumber()
	SigGenType = CscopeUnitA.GetSigGenType()
	CAUType = CscopeUnitA.GetCAUType()
	print("Model:", CAUType,"Serial#:",SerialNumber,"Sig Gen:", SigGenType)
	NumberOfChannels = CscopeUnitA.GetNumberOfChannels()
	print("Channels:",NumberOfChannels)
	IPAddressA = CscopeUnitA.GetIPAddress()
	if IPAddressA.find('.')<1:
		print ("USB Connected")
	else:
		print("ethernet Connected")
		print("IP Address is ",IPAddressA)
	GetAndDisplayUnitInfo(CscopeUnitA)
	if CscopeUnitA.GetNumberOfChannels()==4:
		FourChannel = True
else:
	print("Unit A Failed to connect")



if DualScope:
	# SCOPE UNIT B 
	CscopeUnitB.WaitForConnectionToComplete(5)
	if CscopeUnitB.IsConnected():
		if Debug:
			CscopeUnitB.DoCscopeFunction(9999,0) # Activate Debug window
		print("______________________________")   # Provide some details of Unit B
		print("Hardware (Unit B) connected OK")
		SerialNumber = CscopeUnitB.GetSerialNumber()
		SigGenType = CscopeUnitB.GetSigGenType()
		CAUType = CscopeUnitB.GetCAUType()
		print("Model:", CAUType,"Serial#:",SerialNumber,"Sig Gen:", SigGenType)
		NumberOfChannels = CscopeUnitB.GetNumberOfChannels()
		print("Channels:",NumberOfChannels)
		IPAddressB = CscopeUnitB.GetIPAddress()
		if IPAddressB.find('.')<1:
			print ("USB Connected")
		else:
			print("ethernet Connected")
			print("IP Address is ",IPAddressB)
		GetAndDisplayUnitInfo(CscopeUnitB)
	else:
		print("Unit B Failed to connect")

################# Final Configuration of scope
FreqA = 1000;
FreqB = 1100;
VoltageA = 4.00;
VoltageB = 3.00;               
AcquireStartTime = -0.01;
AcquireStopTime = 0.01;

########### Check the triggering is setup corectly for Dual Scope (with and without linking):
########### Figure Out how the units will trigger based on if the units are linked or not, and which unit is triggering:

if DualScope:
	#Dual Scope:
	if LinkedDualScope:
		#Linked Dual Scope
		if TriggeringUnit == T_TriggeringUnit.T_TriggeringUnit_UnitA:
			CscopeUnitA.SetDualScopelink(T_LinkMasterSlave.T_LinkMasterSlave_Master, UnitATriggerChannel )
			CscopeUnitB.SetDualScopelink(T_LinkMasterSlave.T_LinkMasterSlave_Slave, UnitBTriggerChannel )
		else:
			CscopeUnitA.SetDualScopelink(T_LinkMasterSlave.T_LinkMasterSlave_Slave, UnitATriggerChannel )
			CscopeUnitB.SetDualScopelink(T_LinkMasterSlave.T_LinkMasterSlave_Master, UnitBTriggerChannel )
	else:
		#Seperate (unlinked) Dual Scope
		CscopeUnitA.SetDualScopelink(T_LinkMasterSlave.T_LinkMasterSlave_Unlinked, UnitATriggerChannel)
		CscopeUnitB.SetDualScopelink(T_LinkMasterSlave.T_LinkMasterSlave_Unlinked, UnitBTriggerChannel)
else:
	#Single Scope: Ensure Unit A has Master Slave turned off
	CscopeUnitA.SetDualScopelink(T_LinkMasterSlave.T_LinkMasterSlave_Unlinked, UnitATriggerChannel)

DoAnAcquisition = CscopeUnitA.IsConnected() or (DualScope and CscopeUnitB.IsConnected())


###########  Start the Acquisition  ########### 
########### Keep Looping doing acquisitions ########### 
while DoAnAcquisition: 
	
################# Configuration of acquistion

# Set up Signal Generator A:

	CscopeUnitA.SetupSignalGenerator(FreqA,VoltageA,50,T_SigGenWaveform.T_SigGenWaveform_sine)
	
	# Change Acquistion Values
	CscopeUnitA.AcquireSpec.StartTime = ctypes.c_double(AcquireStartTime);      
	CscopeUnitA.AcquireSpec.StopTime = ctypes.c_double(AcquireStopTime);
	
	if DualScope:

# Set up Signal Generator B:
		CscopeUnitB.SetupSignalGenerator(FreqB,VoltageB,50,T_SigGenWaveform.T_SigGenWaveform_sine)

		# Change Acquistion Values
		CscopeUnitB.AcquireSpec.StartTime = ctypes.c_double(AcquireStartTime);
		CscopeUnitB.AcquireSpec.StopTime = ctypes.c_double(AcquireStopTime);
	

	
	########### Begin Acquisition    ########### 
	print("\r\n# Sampling Started... #")

	if CscopeUnitA.IsConnected():
		UnitA_WaitingForSamples = True;
		CscopeUnitA.BeginSampleCapture(AcquisitionTypeToDo);
	else:
		UnitA_WaitingForSamples = False;

	if DualScope and CscopeUnitB.IsConnected():
		UnitB_WaitingForSamples = True;
		CscopeUnitB.BeginSampleCapture(AcquisitionTypeToDo);
	else:
		UnitB_WaitingForSamples = False;


	########### Wait For Acquisition to Finish
	# Note: if the trigger mode is set to "Triggered" then the trigger may never occur if the parameters for capture are out
	# of bounds of the signal. If the Capture Mode is "Auto" then the time to acquire should be roughly twice the sample period
	# as well as allow some time for communications with hardware.
	print ("Waiting for sampling to complete.")

	FinishedSampling=False
	CancelledByKeypress = False
	TimeLimit = 360 # 20 Second timeout
	StartTime = time()
	LastTime = StartTime
	TimedOut = False

	while (not TimedOut) and (UnitA_WaitingForSamples or UnitB_WaitingForSamples):
		if UnitA_WaitingForSamples:
			if CscopeUnitA.CheckForSampleCaptureComplete():
				UnitA_WaitingForSamples = False
				print("UnitA Sample Capture Complete")
		if UnitB_WaitingForSamples:
			if CscopeUnitB.CheckForSampleCaptureComplete():
				UnitB_WaitingForSamples = False
				print("UnitB Sample Capture Complete")

		KeyPressed = GetKeyPressed()
		if time()-LastTime > 1:
			print(".")
			LastTime = time()
		if KeyPressed != 0:
			print("\r\nAcquision cancelled by keypress")
			CancelledByKeypress = True
			break
		if time()-StartTime > TimeLimit:
			print("\r\nAcquision timeout")
			TimedOut = True
			break
		sleep(0.01)

	# If samples received and not timed out
	if (not TimedOut) and (not CancelledByKeypress):
		# Show the T0dt of the captured samples:
		PrintT0dt("Unit A:", CscopeUnitA)
		if DualScope:
			PrintT0dt("Unit B:", CscopeUnitB)
		# Display Average and DC each channel:

	if FourChannel:		# CS448
		print("ChannelA: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitA.ChannelAData) , CalculateAmplitude(CscopeUnitA.ChannelAData) ) )
		print("ChannelB: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitA.ChannelBData) , CalculateAmplitude(CscopeUnitA.ChannelBData) ) )
		print("ChannelC: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitA.ChannelCData) , CalculateAmplitude(CscopeUnitA.ChannelCData) ) )
		print("ChannelD: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitA.ChannelDData) , CalculateAmplitude(CscopeUnitA.ChannelDData) ) )
		if DualScope:
			print("ChannelE: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitB.ChannelAData) , CalculateAmplitude(CscopeUnitB.ChannelAData) ) )
			print("ChannelF: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitB.ChannelBData) , CalculateAmplitude(CscopeUnitB.ChannelBData) ) )
			print("ChannelG: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitB.ChannelCData) , CalculateAmplitude(CscopeUnitB.ChannelCData) ) )
			print("ChannelH: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitB.ChannelDData) , CalculateAmplitude(CscopeUnitB.ChannelDData) ) )
	else:				# CS320/CS328
		print("ChannelA: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitA.ChannelAData) , CalculateAmplitude(CscopeUnitA.ChannelAData) ) )
		print("ChannelB: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitA.ChannelBData) , CalculateAmplitude(CscopeUnitA.ChannelBData) ) )
		if DualScope:
			print("ChannelC: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitB.ChannelAData) , CalculateAmplitude(CscopeUnitB.ChannelAData) ) )
			print("ChannelD: Average:%.4fV Amplitude:%.4fV" % ( CalculateSampleAverage(CscopeUnitB.ChannelAData) , CalculateAmplitude(CscopeUnitB.ChannelBData) ) )

# Update values ready for next acquisition

	FreqA = FreqA + 100
	FreqB = FreqB + 100
	VoltageA = VoltageA -0.2
	VoltageB = VoltageB +0.2

	FinishedWaitingForKeyPress = False
	while not FinishedWaitingForKeyPress:
		print("\r\n[d]=Display Plot, [enter] or [space] to Capture samples again or [esc] or [q] to quit")
		KeyPressed = WaitForKey(-1);
		if (KeyPressed == 27 or KeyPressed == 81 or KeyPressed == 113 ): #Esc, q or Q
			DoAnAcquisition = False
			FinishedWaitingForKeyPress = True
		if (KeyPressed==68 or KeyPressed==100): #D or d
			DrawPlot(CscopeUnitA,CscopeUnitB,DualScope,FourChannel)
			FinishedWaitingForKeyPress=False
		if (KeyPressed==32 or KeyPressed==13 or KeyPressed==10): #Space, Enter or return
			DoAnAcquisition = True
			FinishedWaitingForKeyPress = True

########### Close all hardware and close the driver
# Close Hardware
print("\r\n# Close Cleverscope Hardware... #")
CscopeUnitA.SendCleverscopeCommand(T_Command.T_Command_Close)
if DualScope:
	CscopeUnitB.SendCleverscopeCommand(T_Command.T_Command_Close)

CscopeUnitA.SendCleverscopeCommand(T_Command.T_Command_Finish)
if DualScope:
	CscopeUnitB.SendCleverscopeCommand(T_Command.T_Command_Finish)

print("\r\n###### FINISHED ######\n")