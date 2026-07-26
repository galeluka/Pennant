// Module path deliberately left as kestudio.
//
// main.go imports "kestudio/internal/store". Renaming the module means editing
// that import too, and this tree has not been through a Go compiler - so the
// rename is a separate, mechanical commit you make after the first successful
// build, not something bundled with code you have not yet run.
//
// go 1.21 is the floor: main.go uses the built-in min().
module kestudio

go 1.21
