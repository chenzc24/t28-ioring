procedure( debugDupPins(libName cellName)
    let((cv trm bb out)
        cv = dbOpenCellViewByType(libName cellName "symbol" nil "r")
        unless(cv return("ERROR: cannot open"))

        out = ""

        /* VSS = terminal index 53 */
        trm = nth(53 cv~>terminals)
        out = strcat(out sprintf(nil "VSS: pins=%d name=%s\n" length(trm~>pins) trm~>name))
        foreach(p trm~>pins
            bb = car(p~>figs)~>bBox
            out = strcat(out sprintf(nil "  fig cx=%g cy=%g\n"
                (car(car(bb))+car(cadr(bb)))/2.0
                (cadr(car(bb))+cadr(cadr(bb)))/2.0))
        )

        /* VSSIB = terminal index 57 */
        trm = nth(57 cv~>terminals)
        out = strcat(out sprintf(nil "VSSIB: pins=%d name=%s\n" length(trm~>pins) trm~>name))
        foreach(p trm~>pins
            bb = car(p~>figs)~>bBox
            out = strcat(out sprintf(nil "  fig cx=%g cy=%g\n"
                (car(car(bb))+car(cadr(bb)))/2.0
                (cadr(car(bb))+cadr(cadr(bb)))/2.0))
        )

        printf("%s" out)
        out
    )
)
