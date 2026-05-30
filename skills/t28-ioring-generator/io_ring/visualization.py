# src/app/utils/visualization.py
import base64
import html
import json
import mimetypes
import os
from urllib.parse import quote


def _calculate_instance_geometry(instances: list, config: dict):
    """
    Pre-calculate geometry (x, y, w, h, rotation) for each instance in Python.
    This ensures layout consistency and removes complex math from JavaScript.
    Coordinates are in 'Canvas Space' (Y increases DOWNWARDS, origin Top-Left).
    """
    chip_w = float(config.get("chip_width", 1000))
    chip_h = float(config.get("chip_height", 1000))
    pad_w = float(config.get("pad_width", 80))
    pad_h = float(config.get("pad_height", 120))
    corner_s = float(config.get("corner_size", 130))
    spacing = float(config.get("pad_spacing", 90))
    order = config.get("placement_order", "clockwise")

    for inst in instances:
        pos_str = inst.get("position", "top_0")
        inst_type = inst.get("type", "pad")
        
        parts = pos_str.split('_')
        side = parts[0].lower()
        
        # Defaults
        x, y, w, h = 0, 0, pad_w, pad_h
        rot = "R0"
        
        # Corner Geometry
        if inst_type == "corner" or "corner" in pos_str:
            w = h = corner_s
            # Map logical corner positions to canvas coordinates
            # Check for explicit corner names like 'top_left', or inferred from 'top_0' if mistakenly labelled
            is_left = "left" in pos_str
            is_right = "right" in pos_str
            is_top = "top" in pos_str
            is_bottom = "bottom" in pos_str
            
            if is_top and is_left:
                x, y = 0, 0
                rot = "R270"
            elif is_top and is_right:
                x, y = chip_w - corner_s, 0
                rot = "R180"
            elif is_bottom and is_left:
                x, y = 0, chip_h - corner_s
                rot = "R0"
            elif is_bottom and is_right:
                x, y = chip_w - corner_s, chip_h - corner_s
                rot = "R90"
            
        else:
            # Pad Geometry
            try:
                # Extract index from 'side_index' (e.g., 'left_0' -> 0)
                idx = int(parts[1]) if len(parts) > 1 else 0
            except ValueError:
                idx = 0

            # --- Coordinate Calculation (Canvas: 0,0 is Top-Left) ---
            
            # Counter-Clockwise Logic (Left: T->B, Bottom: L->R, Right: B->T, Top: R->L)
            if order == "counterclockwise":
                if side == "left":
                    # Vertical pad on Left edge
                    w, h = pad_h, pad_w
                    rot = "R270"
                    x = 0
                    y = corner_s + (idx * spacing)
                elif side == "bottom":
                    # Horizontal pad on Bottom edge
                    w, h = pad_w, pad_h
                    rot = "R0"
                    y = chip_h - pad_h
                    x = corner_s + (idx * spacing)
                elif side == "right":
                    # Vertical pad on Right edge
                    w, h = pad_h, pad_w
                    rot = "R90"
                    x = chip_w - pad_h
                    # Start from bottom (high Y) going up (low Y)
                    # Bottom-most valid position starts above bottom corner
                    # corner_s is the offset from bottom edge
                    # y = (chip_h - corner_s) - pad_width - (idx * spacing)
                    y = (chip_h - corner_s - pad_w) - (idx * spacing)
                elif side == "top":
                    # Horizontal pad on Top edge
                    w, h = pad_w, pad_h
                    rot = "R180"
                    y = 0
                    # Start from right (high X) going left (low X)
                    x = (chip_w - corner_s - pad_w) - (idx * spacing)
            
            # Clockwise Logic (Top: L->R, Right: T->B, Bottom: R->L, Left: B->T)
            else: 
                if side == "top":
                    w, h = pad_w, pad_h
                    rot = "R180"
                    y = 0
                    x = corner_s + (idx * spacing)
                elif side == "right":
                    w, h = pad_h, pad_w
                    rot = "R90"
                    x = chip_w - pad_h
                    y = corner_s + (idx * spacing)
                elif side == "bottom":
                    w, h = pad_w, pad_h
                    rot = "R0"
                    y = chip_h - pad_h
                    x = (chip_w - corner_s - pad_w) - (idx * spacing)
                elif side == "left":
                    w, h = pad_h, pad_w
                    rot = "R270"
                    x = 0
                    y = (chip_h - corner_s - pad_w) - (idx * spacing)

        inst["ui_x"] = x
        inst["ui_y"] = y
        inst["ui_w"] = w
        inst["ui_h"] = h
        inst["ui_rot"] = rot

def get_io_ring_editor_html(initial_json: dict = None) -> str:
    """
    Returns the HTML/JS code for the IO Ring Editor (Puzzle Module).
    If initial_json is provided, it will be pre-loaded into the editor.
    """
    
    # Default empty structure if none provided
    if initial_json is None:
        initial_json = {}
        initial_json_str = "null"
    else:
        # Pre-calculate UI geometry in Python
        if "instances" in initial_json and "ring_config" in initial_json:
             _calculate_instance_geometry(initial_json["instances"], initial_json["ring_config"])
        
        initial_json_str = json.dumps(initial_json)


    # We use a raw string r"..." to avoid Python f-string conflicts.
    # CRITICAL FIX FOR GRADIO:
    # 1. Removed <!DOCTYPE html>, <html>, <head>, <body> tags (Gradio embeds this inside a div)
    # 2. Changed `const ioEditor` to `window.ioEditor` to prevent "Identifier already declared" errors on re-render.
    
    html_content = r"""
    <style>
        .io-editor-body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; display: flex; height: 600px; margin: 0; background: #fff; border: 1px solid #ccc; color: #333; position: relative; }
        .io-sidebar { width: 300px; background: #f8f9fa; border-right: 1px solid #ddd; display: flex; flex-direction: column; padding: 10px; overflow-y: auto; color: #333; }
        .io-main-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; background: #fff; }
        .io-canvas-container { flex: 1; background: #eeeeee; position: relative; overflow: auto; display: flex; justify-content: center; align-items: center; }
        .io-properties-panel { height: 200px; background: #f8f9fa; border-top: 1px solid #ddd; padding: 10px; display: none; color: #333; }
        
        # IO Pad Styles
        .io-pad {
            position: absolute;
            background: #4caf50;
            border: 1px solid #2e7d32;
            color: #ffffff;
            font-size: 10px;
            display: flex;
            justify-content: center;
            align-items: center;
            cursor: pointer;
            box-sizing: border-box;
            user-select: none;
            -webkit-user-select: none; /* safari fallback */
            text-align: center;
            word-wrap: break-word;
            padding: 2px;
            overflow: hidden; /* Ensure text doesn't spill out */
        }
        .io-pad:hover { box-shadow: 0 0 5px rgba(0,0,0,0.5); z-index: 10; transform: scale(1.02); }
        .io-pad.selected { border: 2px solid #ffeb3b; box-shadow: 0 0 8px #ffeb3b; z-index: 20; }
        .io-pad.dragging { opacity: 0.8; z-index: 100; cursor: grabbing; }
        
        .corner-pad { background: #FF6B6B; border-color: #c62828; color: #000; }
        .digital-pad { background: #32CD32; border-color: #228B22; color: #000; }
        .analog-pad { background: #4A90E2; border-color: #3A80D2; color: #000; }

        .palette-item {
            padding: 8px;
            margin: 5px;
            border: 1px solid #ccc;
            background: #eee;
            cursor: grab;
            font-size: 12px;
            color: #333;
        }

        #io-json-output { width: 95%; height: 150px; font-family: monospace; font-size: 11px; margin: 5px; background: #fff; color: #333; border: 1px solid #ccc; }
        .io-controls { padding: 10px; border-bottom: 1px solid #eee; }
        .io-btn { cursor: pointer; padding: 5px 10px; background: #007bff; color: white; border: none; border-radius: 3px; margin-bottom: 5px; width: 100%; }
        .io-btn:hover { background: #0056b3; }
        .io-sidebar label { display: block; margin-top: 5px; font-size: 12px; }
        .io-sidebar input[type="text"] { width: 100%; box-sizing: border-box; }
    </style>

    <div class="io-editor-body">
        <div class="io-sidebar">
            <h3>Component Palette</h3>
            <div class="palette-item" draggable="true" ondragstart="window.ioEditor.startAdd(event, 'PVDD1ANA', 'analog')">Analog VDD (Pad)</div>
            <div class="palette-item" draggable="true" ondragstart="window.ioEditor.startAdd(event, 'PVSS1ANA', 'analog')">Analog VSS (Pad)</div>
            <div class="palette-item" draggable="true" ondragstart="window.ioEditor.startAdd(event, 'PDDW0412SCDG', 'digital')">Digital IO (Pad)</div>
            <div class="palette-item" draggable="true" ondragstart="window.ioEditor.startAdd(event, 'PCORNER', 'null')">Corner Cell</div>

            <div class="io-controls">
                <button class="io-btn" onclick="window.ioEditor.pushToPython()">Sync to Agent</button>
                <button class="io-btn" onclick="window.ioEditor.autoArrange()">Auto-Fix Layout</button>
            </div>
            <h4>Properties</h4>
            <div id="io-props" style="font-size: 12px;">Select an item...</div>
        </div>

        <div class="io-main-area">
            <div class="io-canvas-container" id="io-canvas-container">
                <div id="io-chip-canvas" style="position: relative; background: #fff; box-shadow: 0 0 20px rgba(0,0,0,0.1);">
                    <!-- Pads will be rendered here -->
                </div>
            </div>
            <div class="io-properties-panel" id="io-bottom-panel">
                <h4>Raw JSON</h4>
                <textarea id="io-json-output" aria-label="IO ring layout JSON output" placeholder="Synced layout JSON"></textarea>
            </div>
        </div>
    </div>
    
    	<script>
        // Ensure a stub exists to avoid inline handler errors before full init
        window.ioEditor = window.ioEditor || {};
        window.ioEditor.startAdd = window.ioEditor.startAdd || function(e){ console.warn("ioEditor not ready yet"); };
        console.log("[IOEditor] script tag executing");

        // Check if ioEditor is already defined (Gradio re-render safety)
        if (!window.ioEditor.__initialized) {
            window.ioEditor = {
                __initialized: true,
                config: {}, 
                instances: [],
                scale: 0.5,
                
                chipW: 0, chipH: 0, padW: 80, padH: 120, cornerS: 130,

                selectedId: null,
                dragSrc: null,

                init: function(data) {
                    try {
                        const injectedData = data;
                        if (injectedData) {
                            this.loadData(injectedData);
                        } else {
                             this.loadData({
                                "ring_config": {
                                    "process_node": "T180", "chip_width": 1000, "chip_height": 1000,
                                    "pad_spacing": 90, "pad_width": 80, "pad_height": 120, "corner_size": 130
                                },
                                "instances": [
                                     { "name": "DEMO_PAD", "device": "PVDD1ANA", "position": "top_0", "type": "pad", "domain": "analog" }
                                ]
                            });
                        }
                        console.log("[IOEditor] init completed with", this.instances.length, "instances");
                    } catch(err) {
                        console.error("[IOEditor] init error", err);
                    }
                },

                loadData: function(rawData) {
                    this.config = rawData && rawData.ring_config ? rawData.ring_config : {};
                    this.instances = (rawData && rawData.instances) ? rawData.instances : [];
                    
                    // Force numeric types to prevent string concatenation during layout math
                    this.chipW = parseFloat(this.config.chip_width) || 1000;
                    this.chipH = parseFloat(this.config.chip_height) || 1000;
                    this.padW = parseFloat(this.config.pad_width) || 80;
                    this.padH = parseFloat(this.config.pad_height) || 120;
                    this.cornerS = parseFloat(this.config.corner_size) || 130;
                    this.padSpacing = parseFloat(this.config.pad_spacing) || 90;

                    // Auto-scale to fit view (approx 800x600 visible)
                    const sX = 800 / this.chipW;
                    const sY = 600 / this.chipH;
                    this.scale = Math.min(sX, sY, 0.8); 
                    if (this.scale < 0.1) this.scale = 0.1;

                    this.syncRingConfigFromInstances();

                    this.render();

                    // Persist normalized ring_config immediately so confirm/save works
                    // even when user does not perform any extra interactions.
                    setTimeout(() => this.pushToPython(), 0);
                },

                syncRingConfigFromInstances: function() {
                    const sideMax = { top: -1, right: -1, bottom: -1, left: -1 };

                    this.instances.forEach((item) => {
                        if (!item) return;
                        const t = (item.type || '').toLowerCase();
                        if (t !== 'pad' && t !== 'inner_pad') return;
                        const pos = item.position;
                        if (typeof pos !== 'string') return;
                        const parts = pos.split('_');
                        if (parts.length !== 2) return;
                        const side = parts[0];
                        const idx = parseInt(parts[1], 10);
                        if (!(side in sideMax) || Number.isNaN(idx) || idx < 0) return;
                        if (idx > sideMax[side]) sideMax[side] = idx;
                    });

                    const topCount = sideMax.top >= 0 ? sideMax.top + 1 : 0;
                    const bottomCount = sideMax.bottom >= 0 ? sideMax.bottom + 1 : 0;
                    const leftCount = sideMax.left >= 0 ? sideMax.left + 1 : 0;
                    const rightCount = sideMax.right >= 0 ? sideMax.right + 1 : 0;

                    const width = Math.max(topCount, bottomCount, 1);
                    const height = Math.max(leftCount, rightCount, 1);

                    this.config.width = width;
                    this.config.height = height;
                    this.config.top_count = width;
                    this.config.bottom_count = width;
                    this.config.left_count = height;
                    this.config.right_count = height;

                    const padSpacing = parseFloat(this.config.pad_spacing) || this.padSpacing || 90;
                    const cornerSize = parseFloat(this.config.corner_size) || this.cornerS || 130;
                    const chipWidth = width * padSpacing + cornerSize * 2;
                    const chipHeight = height * padSpacing + cornerSize * 2;

                    this.config.chip_width = chipWidth;
                    this.config.chip_height = chipHeight;
                    this.chipW = chipWidth;
                    this.chipH = chipHeight;
                    this.padSpacing = padSpacing;
                    this.cornerS = cornerSize;
                },

                calculateGeometry: function() {
                    // Full Port of Python _calculate_instance_geometry logic to JS
                    // Ensures that when we add/move items, the UI updates correctly without server roundstop
                    const chipW = parseFloat(this.chipW) || 1000;
                    const chipH = parseFloat(this.chipH) || 1000;
                    const padW = parseFloat(this.padW) || 80;
                    const padH = parseFloat(this.padH) || 120;
                    const cornerS = parseFloat(this.cornerS) || 130;
                    const spacing = parseFloat(this.padSpacing) || 90;
                    const order = this.config.placement_order || 'clockwise';

                    this.instances.forEach((inst) => {
                         const posStr = inst.position || "top_0";
                         const instType = inst.type || "pad";
                         
                         const parts = posStr.split('_');
                         const side = parts[0];
                         
                         let x=0, y=0, w=padW, h=padH, rot="R0";

                         // Corner Geometry
                         if (instType === "corner" || posStr.includes("corner")) {
                            w = cornerS; h = cornerS;
                            let isL = posStr.includes("left");
                            let isR = posStr.includes("right");
                            let isT = posStr.includes("top");
                            let isB = posStr.includes("bottom");

                            if (isT && isL) { x=0; y=0; rot="R270"; }
                            else if (isT && isR) { x=chipW-cornerS; y=0; rot="R180"; }
                            else if (isB && isL) { x=0; y=chipH-cornerS; rot="R0"; }
                            else if (isB && isR) { x=chipW-cornerS; y=chipH-cornerS; rot="R90"; }
                        } else {
                            // Pad Geometry
                            let idx = 0;
                            if (parts.length > 1) idx = parseInt(parts[1]) || 0;
                            
                            if (order === "counterclockwise") {
                                if (side === "left") {
                                    w=padH; h=padW; rot="R270";
                                    x=0; y=cornerS + (idx*spacing);
                                } else if (side === "bottom") {
                                    w=padW; h=padH; rot="R0";
                                    y=chipH-padH; x=cornerS + (idx*spacing);
                                } else if (side === "right") {
                                    w=padH; h=padW; rot="R90";
                                    x=chipW-padH; y=(chipH-cornerS-padW)-(idx*spacing);
                                } else if (side === "top") {
                                    w=padW; h=padH; rot="R180";
                                    y=0; x=(chipW-cornerS-padW)-(idx*spacing);
                                }
                            } else {
                                // Clockwise
                                if (side === "top") {
                                    w=padW; h=padH; rot="R180";
                                    y=0; x=cornerS + (idx*spacing);
                                } else if (side === "right") {
                                    w=padH; h=padW; rot="R90";
                                    x=chipW-padH; y=cornerS + (idx*spacing);
                                } else if (side === "bottom") {
                                    w=padW; h=padH; rot="R0";
                                    y=chipH-padH; x=(chipW-cornerS-padW)-(idx*spacing);
                                } else if (side === "left") {
                                    w=padH; h=padW; rot="R270";
                                    x=0; y=(chipH-cornerS-padW)-(idx*spacing);
                                }
                            }
                        }
                        
                        inst.ui_x = x;
                        inst.ui_y = y;
                        inst.ui_w = w;
                        inst.ui_h = h;
                        inst.ui_rot = rot;
                    });
                },

                render: function() {
                    const canvas = document.getElementById('io-chip-canvas');
                    if (!canvas) {
                        console.warn("[IOEditor] canvas not found yet");
                        return;
                    }

                    // Recalculate Geometry ON EVERY RENDER to ensure updates works
                    this.calculateGeometry();
                    
                    canvas.innerHTML = '';
                    canvas.style.width = (this.chipW * this.scale) + 'px';
                    canvas.style.height = (this.chipH * this.scale) + 'px';


                    // Draw Core Area (Reference)
                    const core = document.createElement('div');
                    core.style.position = 'absolute';
                    core.style.left = (this.padH * this.scale) + 'px';
                    core.style.top = (this.padH * this.scale) + 'px';
                    core.style.width = ((this.chipW - 2 * this.padH) * this.scale) + 'px';
                    core.style.height = ((this.chipH - 2 * this.padH) * this.scale) + 'px';
                    core.style.border = '1px dashed #ccc';
                    core.innerText = "CORE";
                    core.style.textAlign = 'center';
                    core.style.paddingTop = '20%';
                    core.style.color = '#ccc';
                    canvas.appendChild(core);

                    this.instances.forEach((inst, idx) => {
                        const el = document.createElement('div');
                        el.className = 'io-pad';
                        
                        if (inst.type === 'corner') el.classList.add('corner-pad');
                        else if (inst.domain === 'digital') el.classList.add('digital-pad');
                        else el.classList.add('analog-pad');
                        
                        if (idx === this.selectedId) el.classList.add('selected');

                        // Use Python-calculated coordinates if available, otherwise fallback (or 0)
                        // This fixes the layout issues by trusting Python backend logic
                        let x, y, w, h, rotation;
                        
                        if (inst.ui_x !== undefined) {
                            x = inst.ui_x;
                            y = inst.ui_y;
                            w = inst.ui_w;
                            h = inst.ui_h;
                            rotation = inst.ui_rot;
                        } else {
                            // Backup JS Logic if Python inject fails
                            console.warn("Using JS Fallback for", inst.name);
                            const pStr = inst.position || "top_0";
                            const parts = pStr.split('_');
                            const side = parts[0];
                            const idx = parseInt(parts[1]) || 0;
                            const spacing = this.padSpacing;
                            
                            w = (side==='left'||side==='right')? this.padH : this.padW;
                            h = (side==='left'||side==='right')? this.padW : this.padH;
                            
                            if (inst.type === 'corner') { w=this.cornerS; h=this.cornerS; }
                            
                            // Simple Fallback Placement
                            if(side==='top'){ x = this.cornerS + idx*spacing; y = 0; rotation="R180"; }
                            else if(side==='bottom'){ x = this.chipW - this.cornerS - this.padW - idx*spacing; y = this.chipH-this.padH; rotation="R0"; }
                            else if(side==='left'){ x = 0; y = this.chipH - this.cornerS - this.padW - idx*spacing; rotation="R270"; }
                            else if(side==='right'){ x = this.chipW-this.padH; y=this.cornerS + idx*spacing; rotation="R90"; }
                            else { x=0; y=0; rotation="R0"; }
                        }

                        // Inject calculated rotation back into instance for property view
                        inst.rotation = rotation;

                        const scaledW = w * this.scale;
                        const scaledH = h * this.scale;

                        el.style.width = scaledW + 'px';
                        el.style.height = scaledH + 'px';
                        el.style.left = (x * this.scale) + 'px';
                        el.style.top = (y * this.scale) + 'px';
                        el.style.position = 'absolute'; // Reinforce absolute positioning
                        
                        // Text Rotation Logic
                        // We want the text to look like the device is rotated.
                        let textRot = 0;
                        if (rotation === 'R90') textRot = 90;
                        else if (rotation === 'R180') textRot = 180;
                        else if (rotation === 'R270') textRot = 270;
                        
                        // Font scaling based on pad size
                        const minDim = Math.min(scaledW, scaledH);
                        const fontSize = Math.max(6, Math.min(10, minDim / 5));

                        el.style.fontSize = fontSize + 'px';

                        el.innerHTML = `<div style="transform: rotate(${textRot}deg); width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; line-height: 1.1;"><strong>${inst.name || inst.device}</strong><span style="font-size:0.8em; opacity:0.8">${rotation}</span></div>`;
                        
                        el.title = `${inst.name} (${inst.device})\nPos: ${inst.position}\nRot: ${rotation}`;

                        el.draggable = true;
                        el.onclick = (e) => this.selectItem(idx, e);
                        el.ondragstart = (e) => this.handleDragStart(e, idx);
                        el.ondragover = (e) => e.preventDefault();
                        el.ondrop = (e) => this.handleDrop(e, idx);

                        canvas.appendChild(el);
                    });
                },

                selectItem: function(idx, e) {
                    e.stopPropagation();
                    this.selectedId = idx;
                    this.render();
                    this.showProps(this.instances[idx]);
                },

                showProps: function(item) {
                    const container = document.getElementById('io-props');
                    if (!container) return;
                    
                    container.innerHTML = `
                        <label>Name: <input type="text" value="${item.name}" onchange="window.ioEditor.updateProp('name', this.value)"></label>
                        <label>Device: <input type="text" value="${item.device}" onchange="window.ioEditor.updateProp('device', this.value)"></label>
                        <label>Position: <span>${item.position}</span></label>
                        <label>Rotation: <span>${item.rotation || "calc"}</span></label>
                    `;
                },

                updateProp: function(key, value) {
                    if (this.selectedId !== null) {
                        this.instances[this.selectedId][key] = value;
                        this.render();
                        this.pushToPython(); 
                    }
                },

                handleDragStart: function(e, idx) {
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/plain', JSON.stringify({type: 'swap', index: idx}));
                    this.dragSrc = idx;
                },

                startAdd: function(e, device, domain) {
                    e.dataTransfer.effectAllowed = 'copy';
                    e.dataTransfer.setData('text/plain', JSON.stringify({type: 'add', device: device, domain: domain}));
                    this.dragSrc = null;
                },

                handleDrop: function(e, targetIdx) {
                    e.stopPropagation();
                    e.preventDefault();
                    const dataStr = e.dataTransfer.getData('text/plain');
                    if (!dataStr) return;
                    
                    const data = JSON.parse(dataStr);
                    const targetItem = this.instances[targetIdx];
                    
                    if (targetItem.type === 'corner') return; 

                    if (data.type === 'swap') {
                        const srcIdx = data.index;
                        const temp = this.instances[srcIdx];
                        const posA = this.instances[srcIdx].position;
                        const posB = this.instances[targetIdx].position;
                        this.instances[srcIdx].position = posB;
                        this.instances[targetIdx].position = posA;
                        this.instances[srcIdx] = this.instances[targetIdx];
                        this.instances[targetIdx] = temp;
                    } else if (data.type === 'add') {
                        const newItem = {
                            name: "NEW_IO",
                            device: data.device,
                            domain: data.domain,
                            view_name: "layout",
                            type: "pad",
                            position: targetItem.position
                        };
                        this.instances.splice(targetIdx + 1, 0, newItem);
                        this.autoArrange();
                    }
                    
                    this.autoArrange();
                    this.render();
                    this.pushToPython();
                },

                autoArrange: function() {
                    const sides = { top: [], bottom: [], left: [], right: [] };
                    
                    this.instances.forEach(item => {
                        if (item.type !== 'corner') {
                            const side = (item.position || "top_0").split('_')[0];
                            if (sides[side]) sides[side].push(item);
                            else sides.top.push(item);
                        }
                    });
                    
                    Object.keys(sides).forEach(side => {
                        sides[side].forEach((item, idx) => {
                            item.position = `${side}_${idx}`;
                        });
                    });
                    this.syncRingConfigFromInstances();
                    this.render();
                },

                pushToPython: function() {
                    this.syncRingConfigFromInstances();
                    const data = {
                        ring_config: this.config,
                        instances: this.instances
                    };
                    const jsonStr = JSON.stringify(data, null, 2);
                    
                    const bridge = document.querySelector('.io-ring-bridge textarea') || document.querySelector('.io-ring-bridge input');
                    if (bridge) {
                        bridge.value = jsonStr;
                        bridge.dispatchEvent(new Event('input', { bubbles: true }));
                    } else {
                        console.warn("[IOEditor] bridge textarea/input not found");
                    }
                    
                    const debugBox = document.getElementById('io-json-output');
                    if(debugBox) debugBox.value = jsonStr;
                }
            };
        }

        // Initialize with Safety Check
        (function() {
            const maxRetries = 20;
            let attempts = 0;
            
            function tryInit() {
                const canvas = document.getElementById('io-chip-canvas');
                if (canvas) {
                    try {
                        const data = __INITIAL_JSON_DATA__;
                        window.ioEditor.init(data);
                    } catch(err) {
                        console.error("[IOEditor] init dispatch error", err);
                    }
                } else {
                    attempts++;
                    if (attempts < maxRetries) {
                        setTimeout(tryInit, 100);
                    } else {
                        console.error("Failed to initialize IO Editor: Canvas not found.");
                    }
                }
            }
            
            setTimeout(tryInit, 50);
        })();
    </script>
    """
    return html_content.replace("__INITIAL_JSON_DATA__", initial_json_str)

def get_file_preview_html(filename: str, file_map: dict) -> str:
    """
    Generates the HTML content for a file preview modal.
    Logic extracted from original gradio_ui.py to separate concerns.
    """
    if not filename or not file_map:
        return ""
    
    f_info = file_map.get(filename)
    if not f_info:
        return ""
    
    f_path = f_info["path"]
    f_type = f_info["type"]
    
    content_html = ""
    try:
        # URL encode the path to ensure valid src attribute
        safe_path = quote(f_path)
        if f_type == "image":
            # Use Base64 embedding to bypass Gradio /file/ access issues completely
            with open(f_path, "rb") as img_f:
                b64_data = base64.b64encode(img_f.read()).decode('utf-8')
            mime_type, _ = mimetypes.guess_type(f_path)
            if not mime_type:
                mime_type = "image/png"
            content_html = r"""
            <div style="display:flex; flex-direction:column; align-items:center; height:100%;">
                <div style="overflow:hidden; width:100%; height:100%; display:flex; justify-content:center; align-items:center; position:relative; cursor: grab;"
                        onmousedown="if(event.button!==0) return; this.dataset.dragging = 'true'; this.dataset.startX = event.clientX; this.dataset.startY = event.clientY; const img = this.querySelector('img'); this.dataset.initialX = parseFloat(img.getAttribute('data-x') || 0); this.dataset.initialY = parseFloat(img.getAttribute('data-y') || 0); this.style.cursor = 'grabbing'; event.preventDefault();"
                        onmousemove="if(this.dataset.dragging === 'true') { const img = this.querySelector('img'); const dx = event.clientX - parseFloat(this.dataset.startX); const dy = event.clientY - parseFloat(this.dataset.startY); const newX = parseFloat(this.dataset.initialX) + dx; const newY = parseFloat(this.dataset.initialY) + dy; img.setAttribute('data-x', newX); img.setAttribute('data-y', newY); const scale = parseFloat(img.getAttribute('data-scale') || 1); img.style.transform = `translate(${newX}px, ${newY}px) scale(${scale})`; }"
                        onmouseup="this.dataset.dragging = 'false'; this.style.cursor = 'grab';"
                        onmouseleave="this.dataset.dragging = 'false'; this.style.cursor = 'grab';"
                        onwheel="event.preventDefault(); const img = this.querySelector('img'); let scale = parseFloat(img.getAttribute('data-scale') || 1); scale += event.deltaY * -0.001; scale = Math.min(Math.max(0.1, scale), 10); img.setAttribute('data-scale', scale); const x = parseFloat(img.getAttribute('data-x') || 0); const y = parseFloat(img.getAttribute('data-y') || 0); img.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;">
                    <img src="data:__MIME_TYPE__;base64,__B64_DATA__" 
                            style="max-width:100%; max-height:70vh; object-fit:contain; transition: transform 0.05s ease-out;" 
                            ondragstart="return false;"
                            data-scale="1" data-x="0" data-y="0">
                </div>
                <p style="color:#888; font-size:0.8em; margin-top:5px;">Scroll to zoom, drag to move</p>
            </div>
            """.replace("__MIME_TYPE__", mime_type).replace("__B64_DATA__", b64_data)
            
        elif f_type == "json":
            with open(f_path, "r") as f:
                data = json.load(f)
            formatted = json.dumps(data, indent=2)
            content_html = f"<pre style='overflow:auto; max-height:70vh; background:#f5f5f5; padding:10px;'>{html.escape(formatted)}</pre>"
        
        elif f_type == "text":
            with open(f_path, "r", errors="replace") as f:
                content = f.read(10000) # limit
            content_html = f"<pre style='overflow:auto; max-height:70vh; background:#f5f5f5; padding:10px;'>{html.escape(content)}</pre>"
        
        else:
            content_html = f"<div style='padding:20px;'>No preview available for {f_type}</div>"
            
    except Exception as e:
        content_html = f"<div style='color:red;'>Error previewing file: {str(e)}</div>"

    return content_html
