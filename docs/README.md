# Documentation

This directory contains documentation for the `epicsdev_tektronix` package.

## Files

### [SCPI_COMMANDS.md](SCPI_COMMANDS.md)
Comprehensive reference of SCPI command differences between RIGOL and Tektronix oscilloscopes. Includes:
- Horizontal/timebase commands
- Channel control commands
- Trigger configuration commands
- Waveform data acquisition commands
- Setup save/recall commands
- Data format differences and conversion formulas

Use this document when:
- Adapting code from RIGOL to Tektronix
- Understanding the SCPI command mapping
- Debugging communication issues
- Extending functionality

### [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
Complete implementation summary including:
- All files created
- Key adaptations from RIGOL template
- Code quality checks performed
- Usage instructions
- Supported models
- Dependencies

Use this document when:
- Understanding the project structure
- Reviewing what was implemented
- Getting started with the package
- Contributing to the project

## Additional Resources

### Programmer Manual
[Tektronix 4-5-6 Series MSO Programmer Manual](https://download.tek.com/manual/4-5-6-Series-MSO-Programmer_077130524.pdf)

### Related Projects
- [epicsdev_rigol_scope](https://github.com/ASukhanov/epicsdev_rigol_scope) - Original template
- [epicsdev](https://github.com/ASukhanov/epicsdev) - Base EPICS device framework
- [p4p](https://epics-base.github.io/p4p/) - Python PVAccess implementation

## Quick Start

For quick start instructions, see the main [README.md](../README.md) in the repository root.

## Contributing

When contributing documentation:
1. Keep it clear and concise
2. Include code examples where appropriate
3. Reference the Tektronix programmer manual for SCPI details
4. Update this index when adding new documentation files
