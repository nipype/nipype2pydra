from fileformats.generic import File

class Oned(File):
    ext = ".1D"
    binary = True


class Oned(File):
    ext = ".1d"
    binary = True


class Threed(File):
    ext = ".3D"
    binary = True


class Ncorr(File):
    ext = ".ncorr"
    binary = True


class R1(File):
    ext = ".r1"
    binary = True


class All1(File):
    ext = ".all1"
    binary = True


class Dset(File):
    ext = ".dset"
    binary = True


class Head(File):
    ext = ".HEAD"
    binary = True


class Nii[0](File):
    ext = ".nii[0]"
    binary = True


class Unit errts+tlrc(File):
    ext = ".unit errts+tlrc"
    binary = True
