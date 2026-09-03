# epicsdev_tektronix
Python-based EPICS PVAccess server for Tektronix MSO oscilloscopes (4, 5, and 6 Series).

It is based on [p4p](https://epics-base.github.io/p4p/) and [epicsdev](https://github.com/ASukhanov/epicsdev) packages 
and it can run standalone on Linux, OSX, and Windows platforms.

This implementation is adapted from [epicsdev_rigol_scope](https://github.com/ASukhanov/epicsdev_rigol_scope) 
and supports Tektronix MSO series oscilloscopes using SCPI commands as documented in the 
[Tektronix 4-5-6 Series MSO Programmer Manual](https://download.tek.com/manual/4-5-6-Series-MSO-Programmer_077130524.pdf).

## Installation
```pip install epicsdev_tektronix```

For control GUI and plotting:
```pip install pypeto,pvplot```

Control GUI:
```python -m pypeto -c path_to_repository/config -f epicsdev_tektronix```

## Features
- Support for Tektronix MSO oscilloscopes (configurable)
- Real-time waveform acquisition via EPICS PVAccess
- SCPI command interface for scope control
- Support for multiple trigger modes (AUTO, NORMAL, SINGLE)
- Configurable horizontal and vertical scales
- Channel-specific controls (coupling, offset, termination)
- Performance timing diagnostics

## Command-line Options
- `-a, --autosave`: Autosave control
- `-c, --recall`: if given: disable recalling of autosaved PVs 
- `-C, --channels`: Number of channels per device (default: 4)
- `-d, --device`: Device name for PV prefix (default: 'tektronix')
- `-i, --index`: Device index for PV prefix (default: '0')
- `-r, --resource`: VISA resource string (default: 'TCPIP::192.168.1.100::INSTR')
- `-v, --verbose`: Increase verbosity (-vv for debug output)

## Example Usage
```bash
python -m epicsdev_tektronix.mso -r'TCPIP::192.168.1.100::4000:SOCKET'
```
Control GUI:
```python -m pypeto -c path_to_repository/config -f epicsdev_tektronix```

## Supported Tektronix Models
- MSO44, MSO46, MSO48 (4 Series)
- MSO54, MSO56, MSO58 (5 Series)
- MSO64 (6 Series)
- Other MSO series models using compatible SCPI commands

## Performance
Acquisition time of 6 channels, each with 1M of floating point values is 2.0 s. Throughput maxes out at 12 MB/s.
