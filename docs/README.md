# Tektronix MSO Documentation
EPICS PVAccess server for Tektronix MSO and DPO series oscilloscopes.

Tested with TCPI interface on MSO64B and with USB interface on DPO2004B.

## Quick Start

From the project root:

- Install: `pip install -e .`
- Run server: `python -m epicsdev_osc_tektronix_mso`

Example:

- `python -m epicsdev_osc_tektronix_mso -r TCPIP::192.168.1.100::5025::SOCKET -d tektronix -i 0 -v`

## Automatic OPI screen generation

This project includes an automatic Phoebus OPI generator:

- Script: [../opi/generate_simplescope.py](../opi/generate_simplescope.py)
- Output screen: [../opi/simplescope.bob](../opi/simplescope.bob)

Generate the screen from the project root:

- `python opi/generate_simplescope.py '$(DEV):'`

Notes:

- The `prefix` argument sets the PV prefix used by all widgets.
- Default prefix is `$(DEV):`, so it can be supplied via Phoebus macros.
- If needed, install generator dependency: `pip install phoebusgen`.

## Notes

- Prefer `INSTR` VISA endpoints for reliability; `SOCKET` may be faster for large transfers.
- The authoritative runtime behavior is in [../epicsdev_osc_tektronix_mso/__main__.py](../epicsdev_osc_tektronix_mso/__main__.py).
- Main package-level usage and PV overview are in [../README.md](../README.md).
