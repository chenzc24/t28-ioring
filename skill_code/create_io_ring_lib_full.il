
procedure( create_io_ring_lib_full()
    libName = "IO_RING_LIB"
    techLib = "tpd018bcdnv5" ; technology library for T180
    libId = ddGetObj(libName)
    if (libId then
        printf("Library %s already exists\n" libName)
    else
        libId = dbCreateLib(libName techLib)
        printf("Created library %s\n" libName)
    )
    ; Create schematic cellview
    cvId = dbOpenCellViewByType(libName "io_ring_schematic" "schematic" "schematic" "w")
    if (cvId then
        printf("Created schematic cellview\n")
        geSetEditCellView(cvId)
    else
        printf("Failed to create schematic cellview\n")
    )
    "Library and cellview creation done"
)
