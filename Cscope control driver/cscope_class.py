import os,sys



import CleverscopeInterface
from T_AcquireSpec import T_AcquireSpec, T_AcquireAction, T_SigGenWaveform, T_LinkPort, T_TrigChannel, T_TrigSlope
from T_ChannelSpec import T_ChannelSpec, T_Probe, T_GlobalFilter, T_PreFilter20MHz, T_MA_Filter, T_ExpFilter, T_FilterOption, T_Coupling
from T_InterfaceSpec import T_InterfaceSpec, T_Interface
from T_ReplaySpec import T_ReplaySpec
from T_T0dt import T_T0dt
from CleverscopeClasses import T_CAUStatus, T_Command, T_FunctionCommand, T_LinkMasterSlave, T_TriggeringUnit
from time import sleep, time
import ctypes
import numpy as np



class CScope:
    def __init__(self):
        self.scope = None
        self.MaxChannels = 4
        self.ch_names = ["A", "B", "C", "D"]
        self.ch_colors = ["red", "blue", "green", "orange"]


    def connect(self,
        serial_number='EQ10014', # 4 channel heterodyne scope
        start_time_s=-0.1e-3,
        stop_time_s=0.1e-3,
        trigger_level_v=1.0,
        trigger_channel=T_TrigChannel.T_TrigChan_ChanD,
        probe_range_v=(-2.0, 2.0),
        sampling_rate_hz=400e6): # max sampling rate is 400e6

        if self.scope is not None:
            print("Existing connection found. Closing it first...")
            self.disconnect()

        # 2. Calculate Derived Parameters
        duration = stop_time_s - start_time_s
        num_samples = int(duration * sampling_rate_hz)
        max_samples = 4_000_000

        print(f"Initializing Scope ({serial_number})...")

        try:
            # 3. Create the new Object
            # We assign this to a local var first to ensure it works before saving to self
            new_scope = CleverscopeInterface.Cleverscope(
                1, # AcquisitionUnitA
                InterfaceSource=T_Interface.T_Interface_USBFirstFound,
                IPAddr='10.1.5.45',
                TCP_Port=53270,
                SerialNumber=serial_number,
                StartTime=start_time_s,
                StopTime=stop_time_s,
                FrameNum=0,
                NumSamples=num_samples,
                MaximumSamples=max_samples,
                TriggerSource=trigger_channel,
                TriggerLevel=trigger_level_v,
                LinkPort=T_LinkPort.T_LinkPort_Debug,
                ProbeMinVoltage=probe_range_v[0],
                ProbeMaxVoltage=probe_range_v[1],
                ProbeAGain=T_Probe.T_Probe_x1,
                ProbeBGain=T_Probe.T_Probe_x1,
                ProbeCGain=T_Probe.T_Probe_x1,
                ProbeDGain=T_Probe.T_Probe_x1,
                ProbeCoupling=T_Coupling.T_Coupling_DC
            )

            # 4. Attempt Connection
            new_scope.ConnectToHardware()
            new_scope.WaitForConnectionToComplete(5) # Wait up to 5 seconds

            # 5. Verify and Store
            if new_scope.IsConnected():
                self.scope = new_scope  # Only now do we update our class state
                self.is_connected = True
                print(f"Success: Connected to {serial_number}")
                return True
            else:
                print("Error: Hardware created but failed to connect.")
                self.scope = None
                self.is_connected = False
                return False

        except Exception as e:
            print(f"Critical Connection Failure: {e}")
            self.scope = None
            self.is_connected = False
            return False

    def disconnect(self):
        """
        Cleanly disconnects the Cleverscope and frees the USB driver.

        Args:
            scope_obj_name (str): The name of the global variable holding the scope object.
                                  Defaults to 'CscopeUnitA'.
        """
        print(f"\n###### DISCONNECT ROUTINE ######")

        # 1. Check if the variable exists in the global namespace
        if self.scope is None:
            print("No active connection object found to disconnect.")
            return
        else:
            print("Sending Close commands to hardware...")
            try:
                # 2. Send Driver Commands
                # T_Command_Close: Closes the specific unit connection
                self.scope.SendCleverscopeCommand(T_Command.T_Command_Close)

                # T_Command_Finish: Closes the driver library entirely
                self.scope.SendCleverscopeCommand(T_Command.T_Command_Finish)
                print("Hardware handle closed.")

            except Exception as e:
                print(f"Warning: Error sending close commands (Unit might be gone already): {e}")
        print(f"{'_'*40}\n")


    def __del__(self):
        """
        Called when the object is about to be destroyed (e.g., cell overwrite).
        Ensures we don't leave the hardware locked.
        """
        if self.is_connected or self.scope is not None:
            print("CScope Object deleted without disconnect. Forcing cleanup...")
            self.disconnect()

    def update_time_axis(self, start, stop, sampling_rate):
        n_sam = int((stop-start)* sampling_rate)

        try:

            self.scope.AcquireSpec.AcquireAction = T_AcquireAction.T_AcquireAction_Stop
            self.scope.SendCleverscopeCommand(T_Command.T_Command_Update)

            self.scope.AcquireSpec.StartTime = ctypes.c_double(start)
            self.scope.AcquireSpec.StopTime = ctypes.c_double(stop)
            self.scope.ReplaySpec.StartTime = ctypes.c_double(start)
            self.scope.ReplaySpec.StopTime = ctypes.c_double(stop)
            self.scope.UpdateCleverscope()

            self.scope.ReplaySpec.NumSamples = ctypes.c_int32(n_sam)
            self.scope.UpdateCleverscope()
            return True

        except Exception as e:
            print(f"Warning: Error Updating Time Axis: {e}")
            return False

    def update_trigger(self, trig_ch, TriggerLevel=0.5, TriggerType='Rising'):
        """
        Update Trigger Channel and Voltage Level
        """
        try:
            trig_map={"A": T_TrigChannel.T_TrigChan_ChanA,
                     "B": T_TrigChannel.T_TrigChan_ChanB,
                     "C": T_TrigChannel.T_TrigChan_ChanC,
                     "D": T_TrigChannel.T_TrigChan_ChanD}

            slope_map={"Rising": T_TrigSlope.T_TrigSlope_Rising,
                       "Falling": T_TrigSlope.T_TrigSlope_Falling}

            if trig_ch not in trig_map.keys():
                print("Trigger Channel Not Updated, Choose A, B, C, or D...")
                return False
            if TriggerType not in slope_map.keys():
                print("Trigger Slope Not Updated, Choose Rising or Falling...")
                return False

            self.scope.AcquireSpec.TriggerSource = trig_map[trig_ch]
            self.scope.AcquireSpec.TriggerAmplitude = ctypes.c_double(TriggerLevel)
            self.scope.AcquireSpec.TrigSlope = slope_map[TriggerType]
            self.scope.UpdateCleverscope()

            return True

        except Exception as e:
            print(f"Warning: Error Updating Trigger: {e}")
            return False

    def get_single_acquisition(self, acq_type=T_AcquireAction.T_AcquireAction_Automatic, timeout=10.0):
        if self.scope.IsConnected():
            self.scope.BeginSampleCapture(acq_type)
            Waiting = True
        else:
            print("\nError: Scope disconnected!")
            return [None, None]

        # Wait for completion (with 10s timeout)
        TimeoutStart = time()
        while Waiting:
            if self.scope.CheckForSampleCaptureComplete():
                Waiting = False
            elif (time() - TimeoutStart) > timeout:
                print(".", end="", flush=True)
                Waiting = False
                return [None, None]
            sleep(0.01)
        try:
            # Calc Time Axis
            t0 = self.scope.T0dt.T0
            dt = self.scope.T0dt.dt
            n = self.scope.T0dt.n
            t = np.arange(n) * dt + t0

            chA = np.array(self.scope.ChannelAData[:n])
            chB = np.array(self.scope.ChannelBData[:n])
            chC = np.array(self.scope.ChannelCData[:n])
            chD = np.array(self.scope.ChannelDData[:n])

            return [t, (chA, chB, chC, chD)]


        except Exception as e:
            print(f"Warning: Single Acquisition: {e}")
            return [None, None]

        return [None, None]

    def probe_settings(self, show_output=True):
        """
        Reads and optionally prints the current settings for all channels.
        Returns a list of dictionaries containing the settings.
        """
        settings = []
        labels = ['A', 'B', 'C', 'D']

        # --- DECODING MAPS ---
        # We map the integer values from the C-Struct to readable strings
        # (Adjust these if your specific T_Probe definition differs)
        coupling_map = {
            T_Coupling.T_Coupling_DC.value: "DC",
            T_Coupling.T_Coupling_AC.value: "AC"
        }

        # T_Probe usually maps integers to gain steps
        probe_map = {
            T_Probe.T_Probe_x1.value: "x1",
            T_Probe.T_Probe_x10.value: "x10",
            T_Probe.T_Probe_x100.value: "x100",
            T_Probe.T_Probe_x20.value: "x20",
            T_Probe.T_Probe_x50.value: "x50"
        }

        if show_output:
            print(f"\n{'='*65}")
            print(f" CURRENT CHANNEL SETTINGS")
            print(f"{'='*65}")
            print(f" Ch |   Min (V)  |   Max (V)  |  Coupling  |   Probe (Gain)")
            print(f"----|------------|------------|------------|----------------")

        for i in range(self.scope.MaxChannels):
            chan_spec = self.scope.ChannelSpecArray[i]

            # 1. GET RAW VALUES
            # Note: Using standard ctypes field names from the driver
            min_v = chan_spec.Min
            max_v = chan_spec.Max
            c_val = chan_spec.Coupling
            p_val = chan_spec.Probe

            # 2. HANDLE CTYPES OBJECTS
            # Extract .value if it's a ctypes object, otherwise use as is
            if hasattr(min_v, 'value'): min_v = min_v.value
            if hasattr(max_v, 'value'): max_v = max_v.value
            if hasattr(c_val, 'value'): c_val = c_val.value
            if hasattr(p_val, 'value'): p_val = p_val.value

            # 3. DECODE TO STRING
            c_str = coupling_map.get(c_val, f"Unknown({c_val})")
            p_str = probe_map.get(p_val, f"x{p_val}")

            # 4. PRINT
            if show_output:
                print(f"  {labels[i]} | {min_v:10.3f} | {max_v:10.3f} | {c_str:^10} | {p_str:^14}")

            # 5. STORE
            settings.append({
                'channel': labels[i],
                'min_v': min_v,
                'max_v': max_v,
                'coupling': c_str,
                'probe': p_str
            })

        if show_output:
            print(f"{'='*65}\n")

        return settings

    def set_ch_range(self, ChannelIndex, MinVolts, MaxVolts):
            """
            Updates the voltage range for a specific channel.
            ChannelIndex: 0='A', 1='B', 2='C', 3='D'
            """
            if 0 <= ChannelIndex < self.MaxChannels:
                # 1. Update the local structure
                # We use ctypes.c_double to ensure the type matches the driver expectation
                self.scope.ChannelSpecArray[ChannelIndex].Min = ctypes.c_double(MinVolts)
                self.scope.ChannelSpecArray[ChannelIndex].Max = ctypes.c_double(MaxVolts)

                # 2. Push changes to the hardware
                # This sends the T_Command_Update to the driver
                self.scope.UpdateCleverscope()
                return True
            else:
                print(f"Error: Invalid Channel Index {ChannelIndex}. Use 0-3.")
                return False

    def set_ch_coupling(self, ChannelIndex, coupling):
            """
            Updates the coupling type for a specific channel.
            ChannelIndex: 0='A', 1='B', 2='C', 3='D'
            """
            try:
                if 0 <= ChannelIndex < self.MaxChannels:
                    # 1. Update the local structure
                    # We use ctypes.c_double to ensure the type matches the driver expectation
                    if coupling=='AC':
                        self.scope.ChannelSpecArray[ChannelIndex].Coupling = T_Coupling.T_Coupling_AC
                    elif coupling=='DC':
                        self.scope.ChannelSpecArray[ChannelIndex].Coupling = T_Coupling.T_Coupling_DC
                    else:
                        print(f"Error: Invalid Coupling Type {coupling}. Use AC/DC.")
                        return False


                    # 2. Push changes to the hardware
                    # This sends the T_Command_Update to the driver
                    self.scope.UpdateCleverscope()
                    return True
                else:
                    print(f"Error: Invalid Channel Index {ChannelIndex}. Use 0-3.")
                    return False
            except Exception as e:
                print(f"Warning: Failed Setting Channel Coupling: {e}")
                return False

            return False



    def DisplayHardwareInfo(self, show_output=True):
            """
            Queries and displays all static hardware information (Serial, Resolution, Model, IP).
            Returns a dictionary of the values.
            """
            # 1. Prepare C-Types buffers
            # We must create fresh empty buffers for the driver to fill
            sn_array = self.scope.T_SerialNumberArray()
            cau_array = self.scope.T_CAUTypeArray()
            sig_array = self.scope.T_SigGenTypeArray()
            ip_array = self.scope.T_IPAddressArray()

            num_channels = ctypes.c_int32(0)
            adc_res = ctypes.c_int32(0)
            tcp_port = ctypes.c_int32(0)

            # 2. Call the DLL Function
            self.scope.CallCscopeGetHardwareInformation(
                self.scope.AcquisitionUnit,
                ctypes.byref(sn_array), ctypes.c_int32(self.scope.SerialNumberArraySize),
                ctypes.byref(cau_array), ctypes.c_int32(self.scope.CAUTypeArraySize),
                ctypes.byref(num_channels),
                ctypes.byref(adc_res),
                ctypes.byref(sig_array), ctypes.c_int32(self.scope.SigGenTypeArraySize),
                ctypes.byref(ip_array), ctypes.c_int32(self.scope.IPAddressArraySize),
                ctypes.byref(tcp_port)
            )

            # 3. Decode Byte Arrays to Strings
            # We filter out null bytes (0) to get clean Python strings
            def decode_arr(arr):
                try:
                    # Convert ctypes array to bytes, decode ascii, strip nulls/whitespace
                    return bytes(arr).decode('ascii', errors='ignore').strip('\x00').strip()
                except:
                    return "Unknown"

            serial_str = decode_arr(sn_array)
            cau_str = decode_arr(cau_array)
            sig_str = decode_arr(sig_array)
            ip_str  = decode_arr(ip_array)

            # 4. Store in Dictionary
            info = {
                "Serial Number": serial_str,
                "Model Type": cau_str,
                "ADC Resolution": f"{adc_res.value}-bit",
                "Channels": num_channels.value,
                "Interface IP": ip_str,
                "TCP Port": tcp_port.value,
                "SigGen Type": sig_str
            }

            # 5. Print Table
            if show_output:
                print(f"\n{'='*40}")
                print(f"   CLEVERSCOPE HARDWARE INFO")
                print(f"{'='*40}")
                print(f" Serial Number   : {info['Serial Number']}")
                print(f" Model (CAU)     : {info['Model Type']}")
                print(f" ADC Resolution  : {info['ADC Resolution']}")
                print(f" Analog Channels : {info['Channels']}")
                print(f"{'-'*40}")
                print(f" SigGen Option   : {info['SigGen Type']}")
                print(f" IP Address      : {info['Interface IP']}")
                print(f" TCP Port        : {info['TCP Port']}")
                print(f"{'='*40}\n")

            return info

    def GetTriggerSettings(self, show_output=True):
            """
            Reads and prints the current Trigger settings (Source and Level).
            Returns a dictionary of the settings.
            """
            # --- DECODE MAP ---
            # Maps the integer value of T_TrigChannel to a readable string
            # (These values assume standard Cleverscope enum order)
            trig_map = {
                T_TrigChannel.T_TrigChan_ChanA.value: "Channel A",
                T_TrigChannel.T_TrigChan_ChanB.value: "Channel B",
                T_TrigChannel.T_TrigChan_ChanC.value: "Channel C",
                T_TrigChannel.T_TrigChan_ChanD.value: "Channel D",
                T_TrigChannel.T_TrigChan_ExtTrigger.value:   "External",
                T_TrigChannel.T_TrigChan_DigTrig.value:  "Digital"
            }

            mode_map = {
                T_AcquireAction.T_AcquireAction_Automatic.value: "Auto (Force Trig)",
                T_AcquireAction.T_AcquireAction_Triggered.value: "Triggered",
                T_AcquireAction.T_AcquireAction_Single.value:    "Single Shot"
            }

            # 1. READ VALUES
            # Access the internal C-Structure
            raw_source = self.scope.AcquireSpec.TriggerSource
            raw_level  = self.scope.AcquireSpec.TriggerAmplitude
            raw_mode   = self.scope.AcquireSpec.AcquireAction  # This holds the last requested mode

            # 2. HANDLE CTYPES
            if hasattr(raw_source, 'value'): raw_source = raw_source.value
            if hasattr(raw_level, 'value'):  raw_level  = raw_level.value
            if hasattr(raw_mode, 'value'):   raw_mode   = raw_mode.value

            # 3. DECODE
            source_str = trig_map.get(raw_source, f"Unknown ID ({raw_source})")
            mode_str   = mode_map.get(raw_mode,   f"Other ({raw_mode})")

            # 4. PRINT'
            if show_output:
                print(f"\n{'='*40}")
                print(f"   TRIGGER SETTINGS")
                print(f"{'='*40}")
                print(f" Source   : {source_str}")
                print(f" Level    : {raw_level:.3f} V")
                print(f" Mode     : {mode_str}")

                print(f"{'='*40}\n")

            return {
                "source_str": source_str,
                "level_v": raw_level,
                "mode_str": mode_str
            }
