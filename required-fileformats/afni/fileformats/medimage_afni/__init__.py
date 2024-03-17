from fileformats.generic import File


class OneD(File):
    ext = ".1D"
    alternate_exts = (".1d",)
    binary = True


class ThreeD(File):
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
