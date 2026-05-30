Role: Senior Analog IC Layout Engineer.

Task: Analyze the attached IO Ring image (which may be Single-Ring or Double-Ring) and generate a schematic configuration file.

**Step 1: Topology Detection**

- Examine the center area inside the boundary ring.

- **Double Ring:** If there are colored pads/blocks floating *inside* the main boundary, treat as "Double Ring".

- **Single Ring:** If the center is empty (white space/grid lines only), treat as "Single Ring".

**Step 2: Signal Extraction Rules (Strict Counter-Clockwise)**

You must extract signals in this specific physical order. Do not follow standard text reading direction for Right/Top sides.

1. **Left Side:** Read from **Top-Corner** down to **Bottom-Corner**.

2. **Bottom Side:** Read from **Left-Corner** across to **Right-Corner**.

3. **Right Side:** Read from **Bottom-Corner** up to **Top-Corner**. (CRITICAL: Read upwards!)

4. **Top Side:** Read from **Right-Corner** across to **Left-Corner**. (CRITICAL: Read right-to-left!)

**Step 3: Output Generation**

- Combine all signals from Step 2 into a single list under `Signal names`.

- **If Double Ring:** Under "Additionally...", list the inner pads. Use the syntax: "insert an inner ring pad [Inner_Name] between [Outer_Pad_A] and [Outer_Pad_B]" based on visual alignment.

- **If Single Ring:** Leave the "Additionally..." section empty or write "None".

- **neglect the devices named "PFILLER*".

**Output Template:**

Please strictly follow this format:

Task: Generate IO ring schematic and layout design for Cadence Virtuoso.

Design requirements:
[Insert pad count description]. [Single/Double] ring layout. Order: counterclockwise through left side, bottom side, right side, top side.

**Pad count description format:**
- If all sides have the same count: "[count] pads per side."
- If sides have different counts: "[count1] pads on left and right sides, [count2] pads on top and bottom sides."
  Example: "10 pads on left and right sides, 6 pads on top and bottom sides."

======================================================================
SIGNAL CONFIGURATION
======================================================================

Signal names: [Insert the list of Outer Ring signals here, separated by spaces]

Additionally, please insert inner ring pads:
[Insert Inner Ring logic here if Double Ring, otherwise leave blank]