;; Get current cellview information
cv = geGetWindowCellView()
if(cv then
    printf("[Library: %s] [Cell: %s] [View: %s]\n" cv->libName cv->cellName cv->viewName)
    sprintf(nil "%s/%s/%s" cv->libName cv->cellName cv->viewName)
else
    printf("No cellview is currently open\n")
    "No cellview open"
)
