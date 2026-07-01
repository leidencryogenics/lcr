# Control interface to LCR bridge for reading impeadance values.
# Author: Patrick O'Brien
# Date : July 9, 2024
from __future__ import print_function

from sys import stderr

import os
from ctypes import *
from datetime import datetime
import enum
import struct

# Read DLL
class c_p(Structure): # channel parameters
    _pack_ = 1
    _fields_ = [("set_num", c_byte),
                ("set_char", c_wchar),
                ("ch_num", c_byte),
                ("ch_type", c_byte),
                ("freq", c_double),
                ("tau_int", c_double),
                ("I_exc", c_double),
                ("V_exc", c_double),
                ("SNR", c_double),
                ("V_noise", c_double),
                ("P_diss", c_double),
                ("z_type", c_wchar),
                ("z_val", c_double),
                ("z_unit", c_wchar),
                ("timestamp", c_double)
    ]
    
# Write DLL
class b_p(enum.IntEnum):  # Byte type parameters
    Active = 0
    Channeltype = 1
    Channelno = 2
    ReferenceNo = 3
    RLCselect = 4
    Savedata = 5
    Linverted = 6
    Menuactive = 7
    HighGain = 8
    RLCmodel = 9

class d_p(enum.IntEnum):  # Double type parameters
    Frequency = 0
    Voltage = 1
    Current = 2
    IntegrationTime = 3
    RepetitionTime = 4
    GraphFilterTime = 5

# Custom error exceptions
class BridgeInitializationError(Exception):
    """Exception raised for errors in the initialization of the bridge."""

    def __init__(self, error_code, message="Error while initializing the bridge."):
        self.error_code = error_code
        self.message = message
        super().__init__(self.message)

    def __str__(self):
        return f"{self.message} Error code: {self.error_code}"

class EarlyParamException(Exception):
    """Exception raised if a parameter is tried to be read before a measurement is done."""

    def __init__(self, ch_num, param, message="Wait for the next data transfer. Make sure the channel is active."):
        self.ch_num = ch_num
        self.message = message
        self.param = param
        super().__init__(self.message, self.param)

    def __str__(self):
        return f"Parameter {self.param} is not set for channel {self.ch_num}. {self.message}"


# Enable print to stderr
def eprint(*args, **kwargs):
    print(*args, file=stderr, **kwargs)

# Constants for the LCR bridge, initialized as c-types
bridge_type = c_int()  # Type (generation) of the bridge
bridge_sernum = c_int()  # Serial number of the NI DAC card
####
ch_num = c_int(-1)  # Channel being measured
ch_type = c_byte(0)  # channel type 0-2p, 1-4p, 2-4p with input transformer
phase = c_int(-1)  # Measurement phase
err_num = c_int(-1)  # Error code
err_str = create_unicode_buffer(256)  # Error string
z_val = c_double(0)  # Impedance value
z_type = c_wchar()  # Impedance type ("L","C","R")
z_unit = create_unicode_buffer(10)  # Impedance unit ("Ohm","H","F")
t_val = c_double(0)  # Temperature value. Requires calibration coefficients to be filled in the settings dialog
t_unit = create_unicode_buffer(10)  # Temperature unit, as set in calibration settings

c_p = c_p()

measurement_channel_number = 11


class LCR:
    def __init__(self, dllfile, parfile=b"C:\\Impedance Bridge\\ImpBridgeParams.bin", devnum=1):
        """ Initializer. Initializes an LCR bridge connected to @devnum, with
            specified parameters.        

        Arguments: 
            dllfile {str} - Path to the DLL file. It is important that the Python 
                            interperator you are using is compatible with the 
                            architecture of the DLL file.
                           (32-bit DLL for 32-bit Python, etc.)
            parfile {str} - Path to ImpBridgeParams.bin file. If skipped, default
                            path C:\\Impedance Bridge\\ImpBridgeParams.bin is used.
            devnum {int} - Device number. Corresponds to Dev# in NI-MAX. 
            """
        if  struct.calcsize('P') * 8 != 32: # TODO: replace 32 w/ DLL architecture type
            raise ValueError("Python interpreter does not match DLL architecture.")
        if not os.path.exists(dllfile):
            raise ValueError(f"The specified DLL file does not exist: {dllfile}")
        if not os.path.exists(parfile):
            raise ValueError(f"The specified parameter file does not exist: {parfile}")

        self.implib = cdll.LoadLibrary(dllfile) # Import the DLL
        self.parfile = c_char_p(parfile)

        # Set up the bridge.
        self.implib.SetParFilePath(self.parfile) 
        self.implib.LoadParameters()  # Load parameters from file or create new file and load default settings
        self.implib.SetDevice(devnum, byref(bridge_type), byref(bridge_sernum))  
        eprint(f"Connected: LCR bridge type {bridge_type.value}, SN:{bridge_sernum.value}")

        # Set up the parameters
        self.SetByteParam = self.implib.SetByteParam
        self.SetByteParam.argtypes = [c_byte, c_byte, c_byte]

        self.SetRealParam = self.implib.SetRealParam
        self.SetRealParam.argtypes = [c_byte, c_byte, c_double]

        # Initialize the parameter dictionaries for all channels.
        # Store the current parameters (or None if a channel is not
        # being ) for each channel in a dictionary.
        for i in range(measurement_channel_number):
            setattr(self, f'pdict{i}', self.update_param_dict())
            

    def start(self):
        """Start measuring with the LCR bridge."""
        _ = self.implib.ScanStart()  # Returns 0 if no error
        if _ > 0:
            raise BridgeInitializationError(_)
        eprint("Started measuring...")
        
    def stop(self):
        """Stop measuring with the LCR bridge."""
        eprint("Stopping measurement")
        self.implib.ScanStop()

    def status(self, set_num=None):
        """See the currently active channels and their status.

        Args:
            channel (int, optional): Specific channel to check.
                                     If None, checks all channels. Defaults to None.
        """
        channels_to_check = range(measurement_channel_number) if set_num is None else [set_num]

        for i in channels_to_check:
            pdict = getattr(self, f'pdict{i}', {})
            if pdict.get('z_val') is not None:
                eprint(f"Set: {i} is active. Physical channel: {pdict.get('ch_num')}. {pdict.get('z_type')} measurement at {pdict.get('freq'):.2f} Hz. Z = {pdict.get('z_val'):.2f} {pdict.get('z_unit')}")

    def transfer_data(self):
            if self.implib.DataReady():
                # ch_num here is the measurement
                self.implib.TransferData(byref(ch_num), byref(ch_type), byref(z_type), byref(z_val),
                                 z_unit, byref(t_val), t_unit, byref(err_num), err_str)
                self.implib.TransferScanParameters(byref(ch_num), byref(c_p))
                eprint(f"Data ready - Transferring set {c_p.set_num} data...") 

                # Initialize or update the dictionary for the channel
                current_dict = getattr(self, f'pdict{c_p.set_num}', {}) # Get the dict of the corresponding channel
                current_dict = self.update_param_dict(current_dict, c_p)
                current_dict['z_type'] = z_type.value
                current_dict['z_val'] = z_val.value
                current_dict['z_unit'] = z_unit.value
                current_dict['timestamp'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def init_channel(self, set_num, active=1, channeltype=0, channelnum=0, 
                     referenceNo=1, RLCselect=0, Linverted=0, Frequency=13, 
                     Voltage=1e-5, Current=1e-8, IntegrationTime=4, RepetitionTime=1):
        """Initializes a channel on the LCR bridge. If the channel is set to active,
           the measurement will start upon calling start(). If the parameters for a 
           channel are set, they will be saved until they are updated.
           
           Arguments:
               set_num {int} - set number (0-10).
               active {int} - 1 to enable the channel, 0 to disable it.
               channeltype {int} - 0-2probe, 1-4p, 2-4p with input transformer
               channelnum {int} - Set physical channel. 0 is internal reference ( 1 kOhm for 4p, 20 kOhm for 2p)
               referenceNo {int} - Reference impedance for 2p channel. 0-1000 pF, 1-20 kOhm, 2-100 pF
               RLCselect {int} - Set expected load type. 0-R, 1-L, 2-C, 3-Auto
               Linverted {int} - Invert the output polarity of the mutual inductace measurement
               Frequency {int} - Set frequency of AC excitation
               Voltage {int} - Excitation voltage for 2p channel in V
               Current {float} - Excitation current for 4p channel in A
               IntegrationTime {int} - Integration time in seconds
               RepetitionTime {int} - Repetition time in seconds 
        """

        # Default values for byte and double parameters
        default_byte_params = {
            b_p.Active: active,
            b_p.Channeltype: channeltype,
            b_p.Channelno: channelnum,
            b_p.ReferenceNo: referenceNo,
            b_p.RLCselect: RLCselect,
            b_p.Linverted: Linverted
        }

        default_double_params = {
            d_p.Frequency: Frequency,
            d_p.Voltage: Voltage,
            d_p.Current: Current,
            d_p.IntegrationTime: IntegrationTime,
            d_p.RepetitionTime: RepetitionTime
        } 
                
        # Setting byte parameters
        for param, value in default_byte_params.items():
            self.SetByteParam(set_num, param, value)

        # Setting double parameters
        for param, value in default_double_params.items():
            self.SetRealParam(set_num, param, value)

    def readvar(self, set_num, param=None):
        """Read a variable from the parameter dictionary of a measurement set.

        Arguments:
            set_num {int} - measurement set number (0-10).
            param {str} - the c_p parameter to be read.
                          Case-sensitive, no header needed. 
                          e.g. 'Active' instead of 'b_p.Active'
        """

        pdict = getattr(self, f'pdict{set_num}', {})

        if param is None:
            # Print the whole dictionary if no parameter is given
            eprint(pdict)
        elif param not in pdict:
            raise AttributeError(f"{param} is not a valid parameter. Parameters are case-sensitive. Check the README for a full list")
        elif not pdict[param]:
            eprint(f"Parameter {param} is not set/ measured for set {set_num}. Write the parameter and wait for the next data transfer.")
            raise EarlyParamException(set_num, param.name)
        else:
            eprint(f"Channel: {pdict['ch_num']} {param}: {pdict[param]}")
    
    def writevar(self, set_num, param, value):
        """Write a b_p or d_p parameter to the LCR bridge.

        Arguments:
            set_num {int} - measurement set number (0-10).
            param {str} - the b_p/ d_p parameter to be read.
                          Case-sensitive, no header needed. 
                          e.g. 'Active' instead of 'b_p.Active' 
        """
        param = self.parHead(param)  # Get the correct header for the parameter
        if str(param).startswith("b"):
            self.SetByteParam(set_num, param, value)
        elif str(param).startswith("d"):
            self.SetRealParam(set_num, param, value)
        else:
            raise TypeError(f"{param} is not a writeable parameter. Check the README for a full list of byte/ double type parameters.")
        
    def update_param_dict(self, param_dict = None, param=None):
        """ Create a new dictionary or update an existing one with the current values of the c_p object."""
        if param_dict is None:
            # Initialize an empty dictionary
            param_dict = {}

            for param in c_p._fields_:
                param_dict[param[0]] = None

        else:
            if param == c_p:
            # If the parameter dictionary is a c_p object, update the dictionary with the current values
                for field_name, _ in c_p._fields_:
                    value = getattr(c_p, field_name)
                    param_dict[field_name] = value

        return param_dict
    
    def parHead(self, param):
        """Apply the correct header to the given parameter. Used to
        convert dictionary keys to the correct value for the LCR bridge.

        Arguments:
            param {str} - the parameter to be separated.
        Returns:
            {enum ('b_p'/'d_p') or int ('c_p')} - The parameter
            with the correct header."""
        try:
            return getattr(b_p, param)
        except AttributeError:
            # If not found in byte type, check in double type parameters (d_p)
            try:
                return getattr(d_p, param)
            except AttributeError:
                # If not found in either, check in the channel parameters
                try:
                    return getattr(c_p, param)
                except AttributeError:
                    # If not found in all, raise an AttributeError
                    raise AttributeError(f"{param} is not a valid parameter. Parameters are case-sensitive. Check the README for a full list")

    def simple_read(self):
        """ Will transfer the most recent measurement and print it to the console."""
        self.transfer_data() # Transfer the data if it is ready, if not do nothing
        
        # Initialize variables to track the most recent timestamp and channel index
        most_recent_timestamp = datetime.min
        most_recent_channel = None

        for i in range(measurement_channel_number):
            # Retrieve the current channel's dictionary
            current_dict = getattr(self, f'pdict{i}', None)
            # Check if the dictionary is not empty and contains a timestamp value
            if current_dict['timestamp'] is not None: 
                # Parse the timestamp from the current dictionary
                current_timestamp_str = current_dict.get('timestamp', '')
                try:
                    current_timestamp = datetime.strptime(current_timestamp_str, "%Y-%m-%d %H:%M:%S")
                    # Compare with the most recent timestamp found so far
                    if current_timestamp > most_recent_timestamp:
                        most_recent_timestamp = current_timestamp
                        most_recent_channel = i
                except ValueError:
                    # Handle cases where the timestamp string is not properly formatted
                    pass

        # After finding the most recent channel, perform the desired operation
        if most_recent_channel is not None:
            self.readvar(most_recent_channel)
        else:
            print("No valid recent measurement found.")
                
            

