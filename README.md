# epicsdev_osc_tektronix_mso

EPICS PVAccess server for Tektronix oscilloscopes (MSO and DPO families), implemented with `epicsdev`.

Tested with TCPIP interface on MSO64B and USB interface on DPO2004B.

- Main server module: [epicsdev_osc_tektronix_mso/__main__.py](epicsdev_osc_tektronix_mso/__main__.py)
- OPI generator: [opi/generate_simplescope.py](opi/generate_simplescope.py)

## Features

- VISA/SCPI connection to Tektronix instruments via TCP/IP or USB interfaces
- Live waveform publishing over PVAccess
- EPICS PVs reflect live oscilloscope parameters
- Per-channel control/readback:
	- `cNNOnOff`, `cNNCoupling`, `cNNVoltsPerDiv`, `cNNOffset`, `cNNTermination`
	- `cNNWaveform`, `cNNMean`, `cNNPeak2Peak`, `cNNRMS`
- Scope-level PVs:
	- `timePerDiv`, `recLengthS`, `recLengthR`, `samplingRate`, `tAxis`
	- `trigType`, `trigMode`, `trigSource`, `trigSlope`, `trigLevel`, `trigState`, `trigger`
	- `setup`, `instrCmdS`, `instrCmdR`, `acqCount`, `lostTrigs`, `timing`
- Model-aware channel count (when `--channels` is not provided)

## Requirements

- Python 3.11+
- `p4p>=4.2.2`
- `epicsdev>=3.0.1`
- `numpy`
- `pyvisa` + a VISA backend (for example `pyvisa-py`)

## Install

- `pip install epicsdev_tektronix_mso`

## Run

- `python -m epicsdev_osc_tektronix_mso`

Example:

- `python -m epicsdev_osc_tektronix_mso -r TCPIP::192.168.1.100::5025::SOCKET -d tektronix -i 0 -v`

Default PV prefix:

- `tektronix0:`

## Command-line options

- `-a, --autosave` autosave control (optional argument)
- `-c, --recall` disable restore from autosave cache
- `-C, --channels` number of channels (auto-detected when omitted)
- `-d, --device` PV prefix device root (default: `tektronix`)
- `-i, --index` PV prefix index (default: `0`)
- `-r, --resource` VISA resource (default: `TCPIP::192.168.1.100::5025::SOCKET`)
- `-p, --putlogPV` PV used for put logging (default: `putlog:dump`)
- `-v, --verbose` increase verbosity (`-vv` for more)

## OPI

Generate a simple Phoebus screen automatically:

- `python opi/generate_simplescope.py '$(DEV):'`

Output:

- [opi/simplescope.bob](opi/simplescope.bob)

Notes:

- The `prefix` argument defines widget PV names.
- Default prefix is `$(DEV):`, intended for Phoebus macros.
- If needed, install dependency: `pip install phoebusgen`.

## Notes

- `INSTR` VISA endpoints are usually more reliable; `SOCKET` can be faster for large waveform transfers.
- Refer to [docs/README.md](docs/README.md) and [docs/IMPLEMENTATION_SUMMARY.md](docs/IMPLEMENTATION_SUMMARY.md) for implementation details.
