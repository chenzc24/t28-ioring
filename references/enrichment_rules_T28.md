### Universal Ring Structure Principle
- **CRITICAL - Ring Structure Continuity**: IO RING is a **ring structure** (circular), so signals at the beginning and end of the list are adjacent. This applies to both analog and digital signals.
  - **General rule**: In a ring structure, if signals appear in two segments (one at the beginning of the list and one at the end of the list), they are considered contiguous because the list wraps around
  - This principle applies to:
    - **Analog signals**: Voltage domain continuity
    - **Digital signals**: Digital domain continuity

### User Intent Priority
- **Absolute priority**: Strictly follow user-specified signal order, placement order, and all requirements
- **Signal preservation**: Preserve all signals with identical names
- **Placement sequence**: Process one side at a time, place signals and pads simultaneously
- **Voltage domain configuration**:
  - **If user explicitly specifies**: MUST strictly follow user's specification exactly, do not modify or ask for confirmation
  - **If user does NOT specify**: AI must analyze and create voltage domains automatically - every signal must belong to a voltage domain, and every voltage domain must have one PVSS3 provider and one PVDD3 provider (one provider pair)
- **Workflow execution**: Automatically determine workflow entry point based on user input (intent graph file vs requirements), proceed through all steps.

### On-Demand Clarification Trigger (Owned by Draft/Enrichment)

- **Trigger ownership**: The decision of whether to ask the user is owned by draft/enrichment execution, NOT by wizard.
- **Wizard role**: `wizard_T28.md` only defines question templates and output schema.

Must trigger targeted clarification when any of these ambiguity conditions is true:
1. **Device/Pin ambiguity**: Device type or required pin family cannot be uniquely determined from explicit constraints plus rule inference.
2. **Direction ambiguity**: Digital IO direction cannot be resolved with sufficient confidence from explicit constraints and direction rules.
3. **Voltage-domain boundary ambiguity**: A signal/block cannot be uniquely assigned to one analog voltage domain range.

Clarification callback protocol:
1. Pause current step at the ambiguity point.
2. Ask only the minimum questions needed for that ambiguity.
3. Merge returned `wizard_constraints` and continue from the paused point.

Constraint precedence (when no immutable-structure conflict exists):
1. Explicit user prompt constraints
2. On-demand `wizard_constraints`
3. Default enrichment inference

### Workflow Steps
- G1: Signal Classification & Device Selection
  - Step 1: Signal list and classification
  - Step 2: Digital signals classification and pin connection
    - Step 2.1: Digital continuity and context-based re-classification
    - Step 2.2: Digital domain providers and power/ground pin mapping
    - Step 2.3: Digital IO direction and pin mapping
  - Step 3: Analog signals classification, voltage domain assignment, and pin connection
    - Step 3.1: Voltage domain judgment and signal assignment
    - Step 3.2: Analog power/ground device and pin connection (voltage-domain-based)
    - Step 3.3: Analog IO device and pin connection (voltage-domain-based)
    - Step 3.4: Corner device classification
- G2: Generate Intent Graph JSON

## G1: Signal Classification & Device Selection

### Step 1: Signal list and classification (Basic to differ analog vs digital)
  - **CRITICAL - User Voltage Domain Assignment is the PRIMARY Classification Criterion**: 
    - **FIRST check user's voltage domain assignments** - if a signal appears in ANY user-specified analog voltage domain, it is an ANALOG signal and MUST use analog device types, regardless of its name
    - **Signal name is SECONDARY** - do NOT classify signals as digital based on name patterns alone
    - **Digital domain provider count MUST be exactly 4 unique signal names** - if you identify more than 4 different signal names as digital power/ground providers, you have misclassified some signals
  - **CRITICAL - Domain Continuity in Signal Recognition**: When identifying and classifying signals:
    - **Digital signals**: Must form a contiguous block in the signal list (cannot be split by analog signals)
    - **Analog signals**: Must form contiguous blocks (voltage domain continuity)
    - **Ring structure continuity applies** (see "Universal Ring Structure Principle" above)
  - **CRITICAL - Signal Name Context Classification**: If a signal with a digital domain name appears within an analog signal block (surrounded by analog signals) OR is assigned to an analog voltage domain by user, treat it as an analog pad
  - **CRITICAL - Continuity Check Triggers Re-classification**: If digital signals are found to be non-contiguous, re-examine signal recognition - signals appearing in analog voltage domains should be classified as analog signals

**Digital domain power/ground providers MUST be exactly 4 unique signal names:**
- 1 low voltage VDD provider signal name (PVDD1DGZ)
- 1 low voltage VSS provider signal name (PVSS1DGZ)  
- 1 high voltage VDD provider signal name (PVDD2POC)
- 1 high voltage VSS provider signal name (PVSS2DGZ)
- **Note**: Each signal name can have multiple instances (pads), but only 4 unique signal names can be digital domain providers

**If you count more than 4 digital power/ground providers, STOP and re-check:**
- Those extra signals likely belong to analog voltage domains and should use analog device types

---

### Step 2: Digital Signals Classification and pin connection

**Global rules for digital signal classification and pin connection:**
All pin connections for digital signals (both digital IO and digital power/ground) is voltage-domain-based.Except for VSS,other pin connections (VDD, VDDPST, VSSPST) must connect to the corresponding provider signal names in the same voltage domain. The VSS pin connection for all digital pads must be consistent and use the same signal name (the digital domain ground provider signal name).

#### Step 2.1: Digital Domain Continuity and Signal Name Context Classification
**CRITICAL - Digital Domain Continuity:**
- **All digital signals must form a contiguous block** in the signal list/placement order
- **During signal recognition and classification**: Digital signals (digital IO and digital power/ground) must be identified and grouped together as a continuous block, cannot be split by analog signals
- **Ring structure continuity applies** (see "Universal Ring Structure Principle" above)
- This ensures proper power supply and signal routing for the digital domain
- **Note**: Since positions are already given, the continuity requirement primarily applies during signal identification and classification phase
- **CRITICAL - Continuity Check Triggers Re-classification**: **If digital signals are found to be non-contiguous after initial classification, you MUST re-examine signal recognition and classification**. This indicates that some signals with digital domain names may have been misclassified and should be treated as analog signals instead.

**CRITICAL - Signal Name Context Classification:**
- **If a signal with a digital domain name appears within an analog signal block** (surrounded by analog signals on both sides in the signal list), **treat it as an analog pad**, not a digital pad
  - **Digital domain name signals include**: GIOL, VIOL, VIOH, GIOH, DVDD, DVSS, and other digital power/ground signal names
  - **Reason**: These signals are likely serving as power/ground connections for analog devices (e.g., analog devices' VSS pins connect to digital domain ground signal names like GIOL, DVSS)
  - **Device type**: Use analog power/ground device types (e.g., `PVSS1AC`, `PVDD1AC`) instead of digital device types (e.g., `PVSS1DGZ`, `PVDD1DGZ`)
  - **Classification rule**: Check the surrounding signals - if both adjacent signals in the list are analog, classify the signal as analog
  - **This rule ensures digital domain continuity** - by treating isolated digital-named signals within analog blocks as analog pads, the remaining digital signals can form a contiguous block
  - **Examples**: 
    - If DVDD or DVSS appears between analog signals, treat them as analog power/ground (PVDD1AC/PVSS1AC)
    - If GIOL appears between analog signals, treat it as analog ground (PVSS1AC)

#### Step 2.2: Digital Domain Power/Ground assignment and pin connection
- **Standard domain**: `PVDD1DGZ` (standard digital power), `PVSS1DGZ` (standard digital ground)
- **High voltage domain**: `PVDD2POC` (high voltage digital power), `PVSS2DGZ` (high voltage digital ground)

- **CRITICAL - User-Specified Digital Domain Provider Names**: If user explicitly specifies digital domain provider signal names in requirements (e.g., "Digital signals use digital domain voltage domain (VSS/IOVSS/IOVDDL/IOVDDH)"), **MUST use those signal names as digital domain providers**:
  - User-specified low voltage ground → PVSS1DGZ
  - User-specified low voltage power → PVDD1DGZ  
  - User-specified high voltage power → PVDD2POC
  - User-specified high voltage ground → PVSS2DGZ
  - **Do NOT use default names (VIOL/GIOL/VIOH/GIOH) when user specifies different names**
- **CRITICAL - Exactly One Provider Pair Per Voltage Level**: The digital domain **MUST have exactly ONE pair of standard power/ground providers** (PVDD1DGZ/PVSS1DGZ) and **exactly ONE pair of high voltage power/ground providers** (PVDD2POC/PVSS2DGZ). **The digital domain must contain both provider pairs** - one low voltage provider pair and one high voltage provider pair. **Multiple provider pairs of the same voltage level are NOT allowed** in the digital domain. This means:
  - **Exactly ONE low voltage provider pair**: One PVDD1DGZ (provider) and one PVSS1DGZ (provider)
  - **Exactly ONE high voltage provider pair**: One PVDD2POC (provider) and one PVSS2DGZ (provider)
  - **Total**: The digital domain must have exactly 2 provider pairs (one low voltage + one high voltage)
  - **CRITICAL - Exactly 4 Unique Signal Names**: The digital domain **MUST have exactly 4 different signal names** identified as digital voltage domain providers (one for each role: low VDD, low VSS, high VDD, high VSS). **Multiple instances of the same signal name are allowed** (e.g., multiple GIOL signals all using PVSS1DGZ), but **only 4 unique signal names** can be digital domain providers. Any additional signal names with digital-sounding patterns must be classified as analog signals or digital IO, NOT as digital domain providers
- **CRITICAL - Provider Signal Selection Rules**:
  - **Selection rule for multiple signals with identical digital domain names**: If multiple signals with the same digital domain provider name appear in the digital signal block, **ALL of them within the digital block MUST use the same digital voltage domain device type**
  - **CRITICAL - Same name in digital block = Same device type**: Within the digital signal block, if multiple signals share the same name and that name is a digital domain provider, they MUST all use the same digital voltage domain device type. Do NOT mix device types (e.g., do NOT use PVSS1AC for one GIOL and PVSS1DGZ for another GIOL if both are in the digital block)
  - **Other occurrences handling**: Signals with digital domain provider names that appear outside the digital signal block:
    - **If they appear between analog signals**: Apply "Signal Name Context Classification" rule (treat as analog pads, use PVSS1AC/PVDD1AC)
    - **If they appear within the digital signal block**: They must use the same digital voltage domain device type as other instances of the same name
- **CRITICAL - Voltage Domain Assignment Takes Precedence Over Signal Name**: **If a signal is assigned to an analog voltage domain by the user, it MUST use analog device types, regardless of its signal name**. Signal names that might suggest digital domain (e.g., DVDD, DVSS etc.) should be classified based on their voltage domain assignment, NOT based on their name pattern.
  - **Correct approach**: Check user's voltage domain assignments first. If a signal appears in an analog voltage domain, it is an analog signal and must use analog device types (PVDD1AC/PVSS1AC or PVDD3AC/PVSS3AC)
  - **Incorrect approach**: Classifying signals as digital domain providers based solely on signal name patterns, ignoring voltage domain assignments
- **CRITICAL - Error Detection and Re-classification**: If you find more than one pair of low voltage providers or more than one pair of high voltage providers in the digital domain, or if the total count of digital power/ground provider signals is not exactly 4, this indicates:
  1. **Signal recognition error**: Some signals were incorrectly classified as digital domain power/ground providers when they should be:
     - **Analog signals** (if they belong to analog voltage domains as specified by user): Use analog device types (PVDD1AC/PVSS1AC or PVDD3AC/PVSS3AC), NOT digital device types (PVDD1DGZ/PVSS1DGZ/PVDD2POC/PVSS2DGZ)
     - **Digital IO signals** (if they are actual IO signals): Use PDDW16SDGZ device type, NOT digital power/ground device types
  2. **Re-classification needed**: Re-examine the signal list and voltage domain assignments:
     - **CRITICAL**: Signals that appear in **analog voltage domains** (as specified by user) should be classified as **analog signals** and use **analog device types**, NOT digital domain providers, regardless of their signal names
     - Signals that are actual IO signals should be classified as **digital IO signals** (PDDW16SDGZ), NOT digital power/ground providers
     - **Only 4 signals should be digital domain power/ground providers** (one low voltage VDD provider, one low voltage VSS provider, one high voltage VDD provider, one high voltage VSS provider)
     - **All other signals with digital-like names that appear in analog voltage domains must use analog device types**
- **Digital Power/Ground Pin connection**
  - **PVSS1DGZ**: VSS + VDD + VSSPST + VDDPST
    - VSS → own signal name
    - VDD → low voltage domain power signal name
    - VSSPST → high voltage ground signal name
    - VDDPST → high voltage power signal name
  - **PVDD1DGZ**: VSS + VDD + VSSPST + VDDPST
    - VDD → own signal name
    - VSS → low voltage domain ground signal name
    - VSSPST → high voltage ground signal name
    - VDDPST → high voltage power signal name
  - **PVDD2POC**: VSS + VDD + VSSPST + VDDPST
    - VSS → low voltage domain ground signal name
    - VDD → low voltage domain power signal name
    - VSSPST → high voltage ground signal name
    - VDDPST → own signal name
  - **PVSS2DGZ**: VSS + VDD + VSSPST + VDDPST
    - VSS → low voltage domain ground signal name
    - VDD → low voltage domain power signal name
    - VSSPST → own signal name
    - VDDPST → high voltage power signal name

#### Step 2.3: Digital IO Signals Classification and pin connection
- **Examples**: SDI, RST, SCK, SLP, SDO, D0-D13, DCLK, SYNC
- **Device**: `PDDW16SDGZ_H_G`/`PDDW16SDGZ_V_G`
- **Required fields**: `direction` (at instance top level: "input" or "output")
- **Required pins**: VDD + VSS + VDDPST + VSSPST (ONLY these four, no AIO field)

**Direction Judgment Rules:**
- **Common input signals**: SDI (Serial Data In), RST (Reset), SCK (Serial Clock), SLP (Sleep), SYNC (Synchronization), DCLK (Data Clock), control signals
- **Common output signals**: SDO (Serial Data Out), D0-D13 (Data outputs), status signals
- **General rule**: 
  - Signals with "IN" suffix or "I" prefix typically indicate input
  - Signals with "OUT" suffix or "O" prefix typically indicate output
  - Data signals (D0, D1, etc.) are typically outputs unless explicitly specified as inputs
  - Control signals (RST, SLP, etc.) are typically inputs
  - Clock signals (SCK, DCLK) are typically inputs
- **If user explicitly specifies direction**: Use user-specified direction
- **If ambiguous**: Infer from signal name patterns and context, default to "input" for control/clock signals, "output" for data signals

**Digital IO Pin Connection:**
**PDDW16SDGZ**: VSS + VDD + VSSPST + VDDPST
  - VSS → low voltage domain ground signal name
  - VDD → low voltage domain power signal name
  - VSSPST → high voltage ground signal name
  - VDDPST → high voltage power signal name

**CRITICAL - All Digital Domain Pads Must Have 4 Pin Connections:**
- **EVERY digital domain pad** (including digital IO PDDW16SDGZ and digital power/ground PVDD1DGZ/PVSS1DGZ/PVDD2POC/PVSS2DGZ) **MUST have EXACTLY 4 pin_connection entries**:
  - `VDD`: connects to low voltage power signal
  - `VSS`: connects to low voltage ground signal (MUST use the same signal name as all other pads' VSS pin_connection in the entire IO ring)
  - `VDDPST`: connects to high voltage power signal
  - `VSSPST`: connects to high voltage ground signal
- **This applies to ALL digital pads, regardless of whether they are voltage domain providers or digital IO**
- **Do NOT omit any pin** - all 4 pins are mandatory for every digital domain pad
- **CRITICAL - VSS Pin Consistency**: The `VSS` pin_connection label must be **identical to the VSS pin_connection used by all analog pads** in the IO ring (the digital domain low voltage VSS provider signal name)

### Step 3: Analog Signals Classification, Voltage Domain Assignment, and pin connection

#### Step 3.1: Voltage Domain Judgment And Signal Assignment:
**1.Universal Voltage Domain Principles (Apply to Both Priority 1 and Priority 2):**
- **CRITICAL - Use Position Index for Signal Identification**: When processing signals, ALWAYS use **position index** (e.g., index 0, 1, 2...) as the unique identifier, NOT signal name. This is essential because:
  - Same signal name may appear at different positions with different voltage domains
  - Same signal name may have different roles (provider vs consumer) at different positions
- **CRITICAL - Every Signal(including analog IO and analog power/ground) Must Belong to a Voltage Domain**
- **CRITICAL - Voltage Domain Continuity**: 
  - **Single block**: Voltage domain signals should ideally form a contiguous block
  - **Multiple blocks allowed**: If a voltage domain has multiple non-contiguous blocks, this is acceptable **ONLY IF each block has its own complete provider pair** (one VDD provider + one VSS provider within that block)
  - **Ring structure continuity applies** (see "Universal Ring Structure Principle" above)
- **CRITICAL - Provider Pair Per Block**: Each contiguous block of a voltage domain MUST have its own **provider pair** (one VDD provider and one VSS provider within that block)
  - **Provider device types**: PVDD3AC/PVSS3AC (default) or PVDD3A/PVSS3A (only if user explicitly specifies)
  - **Selection rule for multiple signals with identical names** (signals with identical names, e.g., two signals both named "AVDD"):
    - **Default behavior**: If multiple signals with identical names exist **within the same voltage domain** (e.g., two signals both named "AVDD" in the same domain), select the **first occurrence within that domain's range** in placement order as provider (PVDD3AC/PVSS3AC), all others with the same name in that domain become consumers (PVDD1AC/PVSS1AC)
    - **CRITICAL - Different Voltage Domains with Identical Signal Names**: If the same signal name appears in **different voltage domains**, each domain must have its own provider selection. Find the first occurrence **within each domain's specific range** (based on the domain's signal range in the signal list), not the global first occurrence across all domains. Each voltage domain must identify its provider signals independently within its own range.
    - **User override**: If user explicitly requires multiple signals with identical names to be providers, follow user's specification (all specified signals become providers with PVDD3AC/PVSS3AC or PVDD3A/PVSS3A device type)
  - **Each voltage domain** must have its own provider pair - cannot share providers across domains
- **CRITICAL - Multiple Voltage Domains Allowed**: The system can create multiple voltage domains (when user explicitly specifies in Priority 1), each with its own provider pair. **In automatic analysis (Priority 2), use single voltage domain for all analog pads**
- **Consumer device type**: All analog power/ground signals that are NOT selected as providers use `PVDD1AC`/`PVSS1AC` (consumers)
- **CRITICAL - Provider vs Consumer Distinction**: 
  - **Provider**: ONLY the signals that appear in the voltage domain name → uses PVDD3AC/PVSS3AC
  - **Consumer**: ALL other power/ground signals in that domain (even if their name contains VDD/VSS) → uses PVDD1AC/PVSS1AC
  - **Key point**: If domain is "AVSS1/VREFP1", then ONLY AVSS1 and VREFP1 are providers. Any other power/ground signal (like AVDDH1) in this domain MUST use consumer device type (PVDD1AC/PVSS1AC), NOT provider device type

**Priority 1: User Explicit Specification (MUST strictly follow)**
- **When user explicitly specifies voltage domain**: **MUST strictly follow user's specification exactly**, do not modify or ask for confirmation
- **User specification interpretation**:
- Check if signal name appears in user's explicit voltage domain description
  - Check if signal is within a user-specified voltage domain range (inclusive, based on signal order)
  - User-specified voltage domain range: signals within the range belong to that domain
- **Provider selection**:
  - If user explicitly names provider signals → use those signals as providers
  - **If user explicitly requires multiple signals with identical names to be providers** (e.g., two signals both named "AVDD") → use all specified signals as providers (follow user's requirement)
  - **If user does NOT specify which signals are providers** (only specifies domain membership) → select the first occurrence **within that voltage domain's range** in placement order as provider, others become consumers
  - **CRITICAL - Provider Signals Must Use Power/Ground Device Types**: **When a signal is explicitly specified as a voltage domain VDD or VSS provider, it MUST use the corresponding power/ground device type** (PVDD3AC/PVSS3AC or PVDD3A/PVSS3A), **NOT an IO device type** (PDB3AC), even if the signal name suggests it might be an IO signal (e.g., VREFP1, VREFN1). The provider role takes precedence over signal name-based classification.
  - **CRITICAL - Handling Identical Signal Names Across Different Voltage Domains**: 
    - **When the same signal name (e.g., "AVSS1") appears in multiple different voltage domains**, you MUST identify the provider signal **within each domain's specific range**, not the global first occurrence across all domains
    - **Correct approach**: For each voltage domain, find the first occurrence of the provider signal name **within that domain's signal range** (based on the domain's start and end positions in the signal list). Each voltage domain must identify its provider signals independently within its own range.
    - **Example**: If AVSS1 appears in voltage domain 1 (left side, indices 10-15) and voltage domain 2 (bottom side, indices 20-25), you must find the first AVSS1 within domain 1's range (indices 10-15) and the first AVSS1 within domain 2's range (indices 20-25) separately, not use the same global first occurrence for both domains
  - **CRITICAL - Device Type Assignment for Identical Signal Names**: 
    - **When assigning device types, you MUST assign device types based on signal position (index) in the signal list, NOT based on signal name alone**
    - **Each signal instance at a specific position must have its own device type assignment**, even if multiple instances share the same signal name
    - **Correct approach**: For each signal at each position, determine its device type based on:
      - Whether it is a provider or consumer (check if it's the first occurrence within its voltage domain's range)
      - Its voltage domain membership
      - Its position-specific context
    - **Incorrect approach**: Using a dictionary keyed by signal name will cause all instances with the same name to share the same device type, which is wrong when the same signal name appears multiple times with different roles (provider vs consumer)
    - **Example**: If VSSIB appears at index 27 (provider, PVSS3AC) and index 30 (consumer, PVSS1AC) in the same voltage domain, you must assign PVSS3AC to index 27 and PVSS1AC to index 30 separately, not use the same device type for both
  - **Device type for providers**:
    - **If user explicitly specifies PVDD3A/PVSS3A**: Use `PVDD3A`/`PVSS3A` for this domain's provider pair
    - **Otherwise**: Use `PVDD3AC`/`PVSS3AC` for this domain's provider pair

**Priority 2: Automatic Analysis (when user does NOT specify)**
- **When user does NOT specify voltage domain**: AI must analyze and create voltage domains automatically; only invoke user questions when the "On-Demand Clarification Trigger" conditions are met
- **Simplified Approach - Single Voltage Domain for All Analog Pads**:
  - **Default behavior**: All analog signals (analog IO and analog power/ground) belong to **ONE voltage domain**
  - **Ensure continuity**: All analog signals must form a contiguous block in placement order. **Ring structure continuity applies** (see "Universal Ring Structure Principle" above)
- **Voltage Domain Analysis Process**:
  1. **Select ONE VDD signal as VDD provider**:
     - Identify all analog power signals (VDD, AVDD, VDDIB, VDDSAR, etc.)
     - Select the **first occurrence in placement order** as VDD provider
     - **If multiple signals with identical names exist**: Select the first occurrence as provider, others become consumers
     - **Device type for VDD provider**:
       - **If user explicitly specifies PVDD3A** (in general requirements): Use `PVDD3A`
       - **Otherwise**: Use `PVDD3AC`
  2. **Select ONE VSS signal as VSS provider**:
     - Identify the corresponding ground signal of the selected VDD provider (e.g., if VDDIB is selected, select VSSIB)
     - If no corresponding ground signal exists, select the **first occurrence** of any analog ground signal in placement order
     - **If multiple signals with identical names exist**: Select the first occurrence as provider, others become consumers
     - **Device type for VSS provider**:
       - **If user explicitly specifies PVSS3A** (in general requirements): Use `PVSS3A`
       - **Otherwise**: Use `PVSS3AC`
  3. **Assign all other analog signals to the same voltage domain**:
     - **Analog IO signals (PDB3AC)**: All connect to the selected provider pair
     - **Analog power/ground signals**: 
       - If matches the provider pair → use PVDD3AC/PVSS3AC (or PVDD3A/PVSS3A) as provider (but only one instance, already selected in step 1-2)
       - All other analog power/ground signals → use PVDD1AC/PVSS1AC as consumers

**2. CRITICAL: Assign Analog Signals to Their Voltage Domains**
Based on the analysis above, group analog signals into their corresponding voltage domains.Every signal must belong to a voltage domain.

Example:
- Signal list: `VREFN VREFM VREFH VSSSAR VDDSAR VDDCLK VSSCLK VCM VDD_DAT GND_DAT`
- User prompt: from VSSSAR to GND_DAT use VDD_DAT and GND_DAT as voltage domain
- Analog domain 1 (providers: `GND_DAT`, `VDD_DAT`): `VSSSAR VDDSAR VDDCLK VSSCLK VCM GND_DAT VDD_DAT`

#### Step 3.2: Analog Power/Ground Signals Device Type Selection and Pin Connection
**Global rules for analog signal classification and pin connection:**
All pin connections for analog signals (both analog IO and analog power/ground) is voltage-domain-based.Accept for VSS and AIO,other pin connections (TACVDD/TACVSS or TAVDD/TAVSS) must connect to the corresponding provider signal names in the same voltage domain. The VSS pin connection for all analog pads must be consistent and use the same signal name (the digital domain ground signal name).
**Device Type Selection Summary:**
- **Provider** (selected as voltage domain provider): 
  - **If user explicitly specifies PVDD3A/PVSS3A**: Use `PVDD3A`/`PVSS3A`
  - **Otherwise**: Use `PVDD3AC`/`PVSS3AC`
  - **CRITICAL**: Each voltage domain MUST have exactly one PVSS3 provider and one PVDD3 provider (one provider pair)
  - **Multiple provider instances with identical names allowed**: If user explicitly requires multiple signals with identical names to be providers (e.g., two signals both named "AVDD"), all specified signals become providers (PVDD3AC/PVSS3AC or PVDD3A/PVSS3A). Note: This means there can be multiple instances of the same provider signal name, but the domain still has one provider type pair (one VDD provider type + one VSS provider type)
- **Consumer** (all other analog power/ground signals in the same domain that are NOT selected as providers): `PVDD1AC`/`PVSS1AC`

**Device Types:**
- **PVDD1AC/PVSS1AC** (Consumer): Regular analog power/ground, voltage domain consumer
- **PVDD3AC/PVSS3AC** (Provider): Voltage domain power/ground provider
- **PVDD3A/PVSS3A** (Provider, User-Specified Only): Voltage domain power/ground provider with TAVDD/TAVSS pins
  - **CRITICAL**: Only use when user explicitly specifies these device types
  - **Do NOT automatically select** - only use if user explicitly mentions "PVDD3A" or "PVSS3A"
  - Similar to PVDD3AC/PVSS3AC but uses TAVDD/TAVSS instead of TACVDD/TACVSS

**Required Pins:**
- **PVDD1AC**: AVDD + TACVSS/TACVDD + VSS
  - AVDD → own signal name
  - TACVSS → voltage domain ground provider signal name
  - TACVDD → voltage domain power provider signal name
  - VSS → digital domain ground signal name (or default "GIOL")
- **PVSS1AC**: AVSS + TACVSS/TACVDD + VSS
  - AVSS → own signal name
  - TACVSS → voltage domain ground provider signal name
  - TACVDD → voltage domain power provider signal name
  - VSS → digital domain ground signal name (or default "GIOL")
- **PVDD3AC**: AVDD + TACVSS/TACVDD + VSS
  - AVDD → signal name with "_CORE" suffix (e.g., "VDDIB_CORE")
  - TACVDD → own signal name
  - TACVSS → corresponding ground signal in same voltage domain
  - VSS → digital domain ground signal name (or default "GIOL")
- **PVSS3AC**: AVSS + TACVSS/TACVDD + VSS
  - AVSS → signal name with "_CORE" suffix (e.g., "VSSIB_CORE")
  - TACVSS → own signal name
  - TACVDD → corresponding power signal in same voltage domain
  - VSS → digital domain ground signal name (or default "GIOL")
- **PVDD3A**: AVDD + TAVSS/TAVDD + VSS
  - AVDD → signal name with "_CORE" suffix (e.g., "VDDIB_CORE")
  - TAVDD → own signal name
  - TAVSS → corresponding ground signal in same voltage domain
  - VSS → digital domain ground signal name (or default "GIOL")
- **PVSS3A**: AVSS + TAVSS/TAVDD + VSS
  - AVSS → signal name with "_CORE" suffix (e.g., "VSSIB_CORE")
  - TAVSS → own signal name
  - TAVDD → corresponding power signal in same voltage domain
  - VSS → digital domain ground signal name (or default "GIOL")

**VSS Pin Connection Rule:**
- If user specifies digital domain ground signal name → use user-specified name
- If user does NOT specify → use default "GIOL"
- If pure analog design (no digital domain) → use "GIOL"
- VSS pin must use different signal name from TACVSS pin

#### Step 3.3: Analog IO Signals Classification and Pin Connection
**Global rules for digital signal classification and pin connection:**
All pin connections for digital signals (both digital IO and digital power/ground) is voltage-domain-based.
- **Examples**: VCM, CLKP, CLKN, IB12, VREFM, VREFDES, VINCM, VINP, VINN, VREF_CORE
- **Device**: `PDB3AC_H_G`/`PDB3AC_V_G`
- **Required pins**: AIO + TACVSS/TACVDD + VSS
- **AIO pin connection**: Connect to `{signal_name}` net
  - **CRITICAL**: When generating intent graph JSON, AIO pin should connect to `{signal_name}` label (NOT `{signal_name}_CORE`)
  - **Net naming rule**:
    - **For signals without `<>`**: Use signal name directly (e.g., "CLKP" → "CLKP", "VCM" → "VCM")
    - **For signals with `<>`**: Use signal name directly (e.g., "IB<0>" → "IB<0>", "VREF<0>" → "VREF<0>")
- **TACVSS/TACVDD pin connection(Based on voltage domain)**: 
  - TACVSS → VSS provider signal name in the same voltage domain,
  - TACVDD → VDD provider signal name in the same voltage domain
- **CRITICAL - VSS pin connection:** 
  - VSS → digital domain ground signal name (or default "GIOL")

**CRITICAL - Check analog IO and analog power/ground pin connections:**
- if the pins (accept for VSS and AIO) are connected to the correct provider signals in the same voltage domain

### Step 3.4: Corner Devices Classification
- **PCORNER_G**: Digital corner (both adjacent pads are digital)
- **PCORNERA_G**: Analog corner (both adjacent pads are analog, or mixed)
- **No pin configuration required**

**Corner Selection Principle:**
- **CRITICAL - Corner type selection is MANDATORY and cannot be skipped**
- **MUST analyze adjacent pad device types** for each corner individually - this step is required for every corner
- **Corner analysis must be performed BEFORE generating the intent graph JSON** - do not proceed without corner type determination

**Corner Analysis Process (MANDATORY - Must be performed for all 4 corners):**
1. **Corner position names are fixed** (independent of placement_order):
   - Corner names: `top_left`, `top_right`, `bottom_left`, `bottom_right`
   - **CRITICAL**: All 4 corners must be analyzed - do not skip any corner
2. **Identify adjacent pads for each corner** (depends on placement_order):
   - **CRITICAL**: For each corner, you MUST identify the two adjacent pads correctly
   - **CRITICAL - Placement Order Determines Adjacent Pads**: **The adjacent pads for each corner are DIFFERENT depending on whether placement_order is clockwise or counterclockwise**. You MUST use the correct set of adjacent pads based on the placement_order. Using the wrong placement_order's adjacent pad definitions will result in incorrect corner type determination.
   
   **For counterclockwise placement_order:**
   - `top_left`: Adjacent to `top_{width-1}` + `left_0`
   - `top_right`: Adjacent to `top_0` + `right_{height-1}`
   - `bottom_left`: Adjacent to `left_{height-1}` + `bottom_0`
   - `bottom_right`: Adjacent to `bottom_{width-1}` + `right_0`
   
   **For clockwise placement_order:**
   - `top_left`: Adjacent to `left_{height-1}` + `top_0` (**DIFFERENT from counterclockwise**)
   - `top_right`: Adjacent to `top_{width-1}` + `right_0` (**DIFFERENT from counterclockwise**)
   - `bottom_right`: Adjacent to `right_{height-1}` + `bottom_0` (**DIFFERENT from counterclockwise**)
   - `bottom_left`: Adjacent to `bottom_{width-1}` + `left_0` (**DIFFERENT from counterclockwise**)
3. **CRITICAL - Check device types of both adjacent pads**:
   - For each corner, you MUST check the device type of BOTH adjacent pads
   - Device type classification:
     - **Digital devices**: PDDW16SDGZ, PVDD1DGZ, PVSS1DGZ, PVDD2POC, PVSS2DGZ
     - **Analog devices**: PDB3AC, PVDD1AC, PVSS1AC, PVDD3AC, PVSS3AC, PVDD3A, PVSS3A
4. **CRITICAL - Determine corner type** (based on adjacent pad device types):
   - **Both adjacent pads are digital** → Use `PCORNER_G`
   - **Both adjacent pads are analog** → Use `PCORNERA_G`
   - **Mixed (one digital, one analog)** → Use `PCORNERA_G`
   - **CRITICAL**: Corner type determination is based ONLY on adjacent pad device types, not on other factors
5. **Corner insertion order in instances list** (based on placement_order):
   - **Clockwise**: `top_right` → `bottom_right` → `bottom_left` → `top_left`
   - **Counterclockwise**: `bottom_left` → `bottom_right` → `top_right` → `top_left`
6. **CRITICAL - Verify before finalizing**:
   - Verify that all 4 corners have been analyzed
   - Verify that corner type matches adjacent pad device types
   - Verify that corner insertion order is correct based on placement_order


## G2: Generate Intent Graph JSON
- **CRITICAL - JSON Structure**: The intent graph JSON MUST follow the specified structure exactly,including key names and values
### Basic Structure
```json
{
  "ring_config": {
    "width": 4,
    "height": 4,
    "placement_order": "clockwise/counterclockwise"
  },
  "instances": [
    {
      "name": "signal_name",
      "device": "device_type_suffix",
      "position": "position",
      "type": "pad/inner_pad/corner",
      "direction": "input/output (digital IO only, at top level)",
      "pin_connection": {
        "pin_name": {"label": "connected_signal"}
      }
    }
  ]
}
```

### Configuration Examples

**CRITICAL - VSS Pin Connection for ALL Pads (Universal Rule)**:
- **ALL pads in the IO ring** (analog devices: PDB3AC, PVDD1AC, PVSS1AC, PVDD3AC, PVSS3AC, PVDD3A, PVSS3A; digital devices: PDDW16SDGZ, PVDD1DGZ, PVSS1DGZ, PVDD2POC, PVSS2DGZ) **MUST connect their `VSS` pin to the SAME digital domain low voltage VSS provider signal name**
- **CRITICAL - Consistency Requirement**: The `VSS` pin_connection label must be **identical across ALL pads** in the entire IO ring
- **Signal name determination**:
  - If user specifies digital domain provider names, use the user-specified low voltage VSS signal name (e.g., "IOVSS" if user specifies "VSS/IOVSS/IOVDDL/IOVDDH")
  - If user does not specify, use the default digital low voltage VSS signal name (e.g., "GIOL")

**CRITICAL - Device Suffix Rule Based on Position**:
- **Right and Left side devices** must append suffix **`_H_G`** to the base device name
- **Top and Bottom side devices** must append suffix **`_V_G`** to the base device name
- **Examples**:
  - Base device `PDB3AC` at position `left_0` → device field: `PDB3AC_H_G`
  - Base device `PVDD1DGZ` at position `top_0` → device field: `PVDD1DGZ_V_G`

#### Analog IO (PDB3AC)
**Regular signal (no `<>`):**
```json
{
  "name": "VCM",
  "device": "PDB3AC_H_G",
  "position": "left_0",
  "type": "pad",
  "pin_connection": {
    "AIO": {"label": "VCM"},
    "TACVSS": {"label": "VSSIB"},
    "TACVDD": {"label": "VDDIB"},
    "VSS": {"label": "GIOL"}
  }
}
```

**Signal with `<>` (e.g., "IB<0>"):**
```json
{
  "name": "IB<0>",
  "device": "PDB3AC_H_G",
  "position": "left_1",
  "type": "pad",
  "pin_connection": {
    "AIO": {"label": "IB<0>"},
    "TACVSS": {"label": "VSSIB"},
    "TACVDD": {"label": "VDDIB"},
    "VSS": {"label": "GIOL"}
  }
}
```
**Note**: 
- Regular signals: AIO pin connects to `{signal_name}` directly (e.g., "VCM" → "VCM", "CLKP" → "CLKP")
- Signals with `<>`: AIO pin connects to `{signal_name}` directly (e.g., "IB<0>" → "IB<0>", "VREF<0>" → "VREF<0>")
- **Only voltage domain providers (PVDD3AC/PVSS3AC or PVDD3A/PVSS3A) use `_CORE` suffix** (e.g., "VDDIB" → "VDDIB_CORE" for PVDD3AC/PVDD3A AVDD pin)

#### Analog Power - Consumer (PVDD1AC)
```json
{
  "name": "VDD3",
  "device": "PVDD1AC_H_G",
  "position": "left_8",
  "type": "pad",
  "pin_connection": {
    "AVDD": {"label": "VDD3"},
    "TACVSS": {"label": "VSSIB"},
    "TACVDD": {"label": "VDDIB"},
    "VSS": {"label": "GIOL"}
  }
}
```

#### Analog Power - Provider (PVDD3AC)
```json
{
  "name": "VDDIB",
  "device": "PVDD3AC_H_G",
  "position": "left_9",
  "type": "pad",
  "pin_connection": {
    "AVDD": {"label": "VDDIB_CORE"},
    "TACVSS": {"label": "VSSIB"},
    "TACVDD": {"label": "VDDIB"},
    "VSS": {"label": "GIOL"}
  }
}
```

#### Analog Power - Provider (PVDD3A, User-Specified Only)
```json
{
  "name": "VDDIB",
  "device": "PVDD3A_H_G",
  "position": "left_9",
  "type": "pad",
  "pin_connection": {
    "AVDD": {"label": "VDDIB_CORE"},
    "TAVSS": {"label": "VSSIB"},
    "TAVDD": {"label": "VDDIB"},
    "VSS": {"label": "GIOL"}
  }
}
```
**Note**: Only use PVDD3A/PVSS3A when user explicitly specifies these device types. Otherwise, use PVDD3AC/PVSS3AC.

#### Analog Power - Provider (PVSS3A, User-Specified Only)
```json
{
  "name": "VSSIB",
  "device": "PVSS3A_H_G",
  "position": "left_10",
  "type": "pad",
  "pin_connection": {
    "AVSS": {"label": "VSSIB_CORE"},
    "TAVSS": {"label": "VSSIB"},
    "TAVDD": {"label": "VDDIB"},
    "VSS": {"label": "GIOL"}
  }
}
```
**Note**: Only use PVSS3A when user explicitly specifies this device type. Otherwise, use PVSS3AC.

#### Digital IO (PDDW16SDGZ)
```json
{
  "name": "RSTN",
  "device": "PDDW16SDGZ_H_G",
  "position": "left_0",
  "type": "pad",
  "direction": "input",
  "pin_connection": {
    "VDD": {"label": "IOVDDL"},
    "VSS": {"label": "VSS"},
    "VDDPST": {"label": "IOVDDH"},
    "VSSPST": {"label": "IOVSS"}
  }
}
```
**Note**: `direction` is at instance top level, `pin_connection` contains ONLY VDD/VSS/VDDPST/VSSPST

#### Inner Ring Pad (Digital IO)
```json
{
  "name": "D15",
  "device": "PDDW16SDGZ_V_G",
  "position": "top_2_3",
  "type": "inner_pad",
  "direction": "output",
  "pin_connection": {
    "VDD": {"label": "VIOL"},
    "VSS": {"label": "GIOL"},
    "VDDPST": {"label": "VIOH"},
    "VSSPST": {"label": "GIOH"}
  }
}
```
**Note**: Digital IO inner ring pads MUST include `direction` field

#### Corner
```json
{
  "name": "CORNER_TL",
  "device": "PCORNER_G",
  "position": "top_left",
  "type": "corner"
}
```

## Task Completion Checklist

### Device & Configuration
- [ ] Device types correctly selected (voltage domain judgment accurate)
- [ ] Corner types correctly determined based on adjacent pads
- [ ] **CRITICAL: Provider signals use power/ground device types (PVDD3AC/PVSS3AC or PVDD3A/PVSS3A), NOT IO device types (PDB3AC)**, even if signal name suggests IO (e.g., VREFP1, VREFN1)
- [ ] Device suffixes correct (_H_G for left/right, _V_G for top/bottom)
- [ ] All required pins configured per device type
- [ ] TACVSS/TACVDD configured for all analog devices, and all VSS pins connect to the same digital domain low voltage VSS signal name (user-specified or default "GIOL")
- [ ] **Analog IO (PDB3AC) AIO pin connects to `{signal_name}` label** (NOT `{signal_name}_CORE`)
  - Regular signals: `{signal_name}` (e.g., "CLKP" → "CLKP", "VCM" → "VCM")
  - Signals with `<>`: `{signal_name}` (e.g., "IB<0>" → "IB<0>")
- [ ] **Analog voltage domain providers (PVDD3AC/PVSS3AC or PVDD3A/PVSS3A) AVDD/AVSS pins connect to `{signal_name}_CORE` label**
  - Regular signals: `{signal_name}_CORE` (e.g., "VDDIB" → "VDDIB_CORE")
  - Signals with `<>`: `{prefix}_CORE<{index}>` (e.g., "VDD<0>" → "VDD_CORE<0>")
- [ ] **PVDD3A/PVSS3A device selection**: Only used when user explicitly specifies these device types
- [ ] **PVDD3A/PVSS3A pin connections**: TAVDD/TAVSS configured correctly (similar to TACVDD/TACVSS but different pin names)
- [ ] `direction` field configured for all digital IO (including inner ring)
- [ ] Digital IO pin_connection contains ONLY VDD/VSS/VDDPST/VSSPST

### Final Confirmation
- [ ] All checklist items completed
- [ ] User satisfied and confirms completion
- [ ] No unresolved errors

