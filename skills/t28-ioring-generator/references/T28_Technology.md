# T28 Technology - DRC Rules

Process-specific design rule check (DRC) parameters for 28nm technology node.

## DRC Rules

### Minimum Dimensions
- **Minimum spacing**: ≥ 0.05 µm
  - Applies to spacing between metal features, routing wires, and structures
- **Minimum width**: ≥ 0.05 µm
  - Applies to all metal line widths
- **Critical spacing**: ≥ 0.1 µm
  - Applies to spacing involving connection points (pins, vias, terminals)
  - Applies to routing wire endpoints to other structures
  - Required for DRC compliance and manufacturing robustness

### Minimum Area
- **Minimum polygon area**: ≥ 0.017 µm² (if applicable)
  - Check DRC reports for minimum area violations

## Metal Layers

- **Allowed layers**: M1, M2, M3, M4, M5, M6, M7
- **Naming convention**: Use "M" prefix (e.g., M1, M2, M7)

## Parameter Precision

- **Parameters**: Two decimal places (e.g., 0.05, 0.75)
- **Coordinates**: Five decimal places for geometric calculations (e.g., 0.12345)

## Usage

These DRC rules apply to all IO ring designs targeting the 28nm process node. Always validate designs against these minimum dimensions before finalizing layouts.
