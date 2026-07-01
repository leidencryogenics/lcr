Filename: README

Author: Patrick O'Brien `<patrick@leidencryogenics.com>`

This python script acts as a controller for the Leiden Cryogenics
impedance bridge. 

The heart of the resistance bridge is a National Instruments 
NI-USB-6215 unit which performs analog-digital and DA conversion. 
The downside is that there is no plug-and-play serial communication. 
The incoming data needs to be unpacked on the control PC side. 

The brain of the resistance bridge is a dynamic link library (DLL) 
file. The DLL file writes instructions and reads measurement data.
Communication to the DLL file is done via python in this driver wrapper. The 32-bit
architecture of this DLL file has to match that of your python 
interperator. This means running the LCR wrapper from a 32-bit
python environment (more below). 

The wrapper is not configured to do temperature conversion, altough 
this is possible if the calibration coefficients are filled-in in 
the settings dialog of the Lab-View program (or Otherwise).  

**Setup**

Follow the installation steps according to page 7 of the LCR Bridge type C3 manual. 
The NIMAX program is needed for communication with the NI-USB-6215 unit, and the 
labview software is needed for initial calibration. 

Setup a new 32-bit python environment with 

```
conda create -n [env_name]
conda activate [env_name]
conda config --env --set subdir win-32
conda install python
```

For a simple run, just load the script by

```
python -i "path\to\file\lcr.py"
```

which would load the entire script in the interpretor. For more complicated uses 
please use import. 

To initiate a controller run

```python
>>> d = LCR(r"path\to\file\ImpBridgeDll.dll", devnum=1) 
```

where the argument is the address of the DLL file linked to the LCR bridge, and the
device number for the NIMAX program. The device will verify if you are connected. 

To initialize channels, use

```python
>>> d.init_channel(...)
```

To start/ stop the measurements, run

```python
>>> d.start()
>>> d.stop()
```

To transfer the most recent measurement to the control PC, use

```python
>>> d.transfer_data()
```

To read the status of (all) the active measurement channels, run

```python
>>> d.status()
```

Or to read all the data in a measurement channel, run

```python
>>> d.readvar([0-10])
```

**Using the bridge**

The bridge is able to do 11 measurements simultaneously, and has 11 physical
channels (x4 2-point and x6 4-point measurement channels, and one channel for 
internal reference). 

The measurement parameters of a set [0-10] are set via 

```python
>>> d.init_channel([0-10])
```

where the argument is an integer corresponding to the [0-10]th measurement. Other
arguments such as frequency and voltage can be set. By default these are 
configured for a resistance measurement. Typical settings for resistors, capacitors,
and inductors are in the labview software after calibration. 

Specific parameters can be updated after initialization of a channel by using

```python
>>> d.writevar([0-10], [param], [value])
```

The physical channel is determined upon initialization by the "channel_no" 
parameter, and is output after a measurement as 'ch_num'. These DO NOT necessarily 
correspond to the set numbers used throughout the wrapper. This is to account
for the fact that the bridge can do multiple measurements on the same sample / same
physical channel. 

In practice we only use one measurement per physical channel for our thermometry. 

The LCR bridge remembers the settings from a previous run. All of the active 
measurement sets will continue to be sequentially measured until a channel is 
de-activated (by calling init_channel again, with active=0). 

A channel/set can be measured more frequently (relative to the other channels) by 
lowering the RepetitionTime parameter (default = 4s). Useful if more frequent data
is required e.g. if using a certain thermometer for PID control.

Measurement data is transfered to the control PC via

```python
>>> d.transfer_data()
```

which returns the most recent measurement (or nothing). New data is not transfered 
automatically via the wrapper. 

**List of parameters**

The DLL file sees a distinction between parameters. Broadly, "Channel parameters" 
are measurement data, and can be read with the LCR wrapper by calling .read_var()

"Byte type/ Double type parameters" are for setting-up measurements, and can be 
written to the LCR bridge via .writevar() / .init_channel() at anytime. 

There is a mapping between some parameters. 

**Byte type parameters - b_p (int)**
- Active  # 0-off, 1-on
- Channeltype * # Set channel type. 0-2p, 1-4p, 2-4p with input transformer
- Channelno * # Set physical channel. 0 is internal reference (1 kOhm for 4p, 20 kOhm for 2p)
- ReferenceNo # Reference impedance for 2p channel. 0-1000 pF, 1-20 kOhm, 2-100 pF
- RLCselect # Set expected load type. 0-R, 1-L, 2-C, 3-Auto
- Savedata
- Linverted # Invert the output polarity of the mutual inductance measurement
- Menuactive
- HighGain
- RLCmodel

**Double type parameters - d_p (float)**
- Frequency * # Reference frequency (Hz)
- Voltage * # Excitation voltage (V)
- Current * # Excitation current (A)
- IntegrationTime * # (s)
- RepetitionTime # (s)
- GraphFilterTime # (s)

**Channel parameters - c_p**
- set_num # Position of measurement channel in sequence, starts at 0
- set_char # Position of measurement channel in sequence, starts at A
- ch_num *b (see above, b_p)
- ch_type *b
- freq *d
- tau_int *d
- I_exc *d
- V_exc *d
- SNR # Signal-to-noise ratio
- V_noise # Voltage noise (V)
- P_diss # Power dissipation (W)
- z-type *b
- z-val # Impedance value (Ohms/ H/ F)
- z-unit # Unit

A quirk of the DLL file is that only parameters of the most recent measurement
channel can be read. To mitigate this, all of the recent parameters are stored 
locally in a set specific dictionary so that any parameters 
can be read at any time AFTER they have been measured once. 
