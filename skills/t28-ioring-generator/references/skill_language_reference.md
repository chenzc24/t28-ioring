# SKILL Programming Language Reference

Quick reference for Cadence Virtuoso SKILL language. Use this when reading, debugging, or modifying generated `.il` scripts.

---

## Syntax Basics

### Variables & Data Types

```skill
; Variables
myVar = 5
myString = "hello"
myList = list(1 2 3)

; Numbers
intValue = 42
floatValue = 3.14

; Strings
str = "Hello World"
formatted = sprintf(nil "Value: %d" 42)

; Lists
myList = list(1 2 3 4 5)
emptyList = list()
```

### Comments

```skill
; Single line comment

/*
Multi-line
comment
*/
```

---

## Control Flow

```skill
; If/else
if( condition then
  ; true branch
else
  ; false branch
)

; When (if without else)
when( condition
  ; do something
)

; Unless (inverse if)
unless( condition
  ; do this if condition is false
)
```

---

## Loops

```skill
; For loop
for( i 1 10
  printf("Count: %d\n" i)
)

; Foreach loop
foreach( item myList
  printf("Item: %L\n" item)
)
```

---

## Functions

```skill
; Define
procedure( myFunction(arg1 arg2)
  arg1 + arg2
)

; Call
result = myFunction(5 3)
```

---

## Virtuoso API Essentials

### Cellview Operations

```skill
; Get current cellview
cv = geGetEditCellView()
cv = geGetWindowCellView()

; Access properties
cv~>libName    ; library name
cv~>cellName   ; cell name
cv~>viewName   ; view name
cv~>shapes     ; list of shapes
cv~>instances  ; list of instances
cv~>bboxes     ; bounding boxes
```

### Geometry Creation

```skill
; Create rectangle
dbCreateRect(cv list("metal1" "drawing") list(0:0 10:10))

; Create path
dbCreatePath(cv list("metal1" "drawing") list(0:0 100:0 100:100) 0.5)

; Create via
dbCreateVia(cv list("via1" "drawing") 50:50 list("VIA12"))
```

### Instance Operations

```skill
; Create instance
dbCreateInst(cv masterCV cellName list(x y) "instanceName" rotation)

; Access instance properties
inst~>cellName
inst~>libName
inst~>viewName
inst~>origin    ; position
inst~>orient    ; orientation
```

---

## Coordinate System

```skill
; Points (x:y)
pt1 = 0:0
pt2 = 10:20

; Access coordinates
x = xCoord(pt1)
y = yCoord(pt1)

; Bounding box (lower-left : upper-right)
bbox = list(0:0 100:100)
```

---

## Error Handling & Safety

```skill
; Check if variable exists
if( boundp('myVar) then
  printf("Variable exists\n")
)

; Safe cellview access
when( cv = geGetEditCellView()
  printf("Cell: %s\n" cv~>cellName)
)

; Nil check
if( cv then
  ; cv is valid, proceed
else
  printf("Error: No cellview open\n")
)
```

---

## Loading & Running Scripts

```skill
; Load a SKILL file
load("path/to/file.il")

; From CIW (Command Interpreter Window)
; CIW> load("my_script.il")

; Load with error handling
if( isFile("path/to/file.il") then
  load("path/to/file.il")
else
  printf("Error: File not found\n")
)
```

---

## Common Debugging Patterns

### Inspect Objects

```skill
; Print all instance names in cellview
foreach( inst cv~>instances
  printf("Instance: %s at %L\n" inst~>cellName inst~>origin)
)

; Print all shape layers
foreach( shape cv~>shapes
  printf("Layer: %s\n" shape~>layerName)
)
```

### Common Runtime Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `*Error* dbCreateRect: invalid cellview` | cv is nil | Check `geGetEditCellView()` returned valid cv |
| `*Error* eval: unbound variable` | Variable not defined | Add `boundp()` check before use |
| `*Error* dbCreateInst: cell not found` | Wrong lib/cell/view | Verify library path and cell name |
| `*Error* syntax error` | Missing parenthesis or wrong arg order | SKILL uses prefix `(func arg1 arg2)`, check parens match |
| `*Error* layer not found` | Invalid layer-purpose pair | Check layer exists in tech file (e.g., `"M1" "drawing"`) |

---

## Quick Reference Table

| Category | Function | Purpose |
|----------|----------|---------|
| Cellview | `geGetEditCellView()` | Get current editing cellview |
| Cellview | `geGetWindowCellView()` | Get window cellview |
| Cellview | `dbOpenCellViewByType(lib cell view "a")` | Open cellview for append |
| Geometry | `dbCreateRect(cv layer bbox)` | Create rectangle |
| Geometry | `dbCreatePath(cv layer points width)` | Create path |
| Geometry | `dbCreateVia(cv layer point viaDef)` | Create via |
| Instance | `dbCreateInst(cv master name pos orient)` | Create instance |
| List | `list(a b c)` | Create list |
| List | `car(lst)` / `cdr(lst)` | First element / rest |
| List | `length(lst)` | List length |
| String | `sprintf(nil fmt args)` | Format string |
| String | `strlen(str)` | String length |
| Output | `printf(fmt args)` | Print to CIW |
| File | `load("path")` | Load SKILL file |
| Check | `boundp('var)` | Check variable exists |
| Check | `isFile("path")` | Check file exists |