"""Module to put any functions that are referred to in the "callables" section of ProbTrackX2.yaml"""

import warnings
import re
from hashlib import md5
import shutil
import os
from pathlib import Path
from fileformats.generic import File, Directory
from glob import glob
import os.path as op
import logging
import hashlib
import attrs
import subprocess as sp
import simplejson as json
from fileformats.generic import File
import posixpath


def out_dir_default(inputs):
    return _gen_filename("out_dir", inputs=inputs)


def out_dir_callable(output_dir, inputs, stdout, stderr):
    outputs = _list_outputs(
        output_dir=output_dir, inputs=inputs, stdout=stdout, stderr=stderr
    )
    return outputs["out_dir"]


related_filetype_sets = [(".hdr", ".img", ".mat"), (".nii", ".mat"), (".BRIK", ".HEAD")]


_cifs_table = _generate_cifs_table()


fmlogger = logging.getLogger("nipype.utils")


IFLOGGER = logging.getLogger("nipype.interface")


class FSLCommandInputSpec(CommandLineInputSpec):
    """
    Base Input Specification for all FSL Commands

    All command support specifying FSLOUTPUTTYPE dynamically
    via output_type.

    Example
    -------
    fsl.ExtractRoi(tmin=42, tsize=1, output_type='NIFTI')
    """

    output_type = traits.Enum("NIFTI", list(Info.ftypes.keys()), desc="FSL output type")


class FSLCommand(CommandLine):
    """Base support for FSL commands."""

    input_spec = FSLCommandInputSpec
    _output_type = None

    _references = [
        {
            "entry": BibTeX(
                "@article{JenkinsonBeckmannBehrensWoolrichSmith2012,"
                "author={M. Jenkinson, C.F. Beckmann, T.E. Behrens, "
                "M.W. Woolrich, and S.M. Smith},"
                "title={FSL},"
                "journal={NeuroImage},"
                "volume={62},"
                "pages={782-790},"
                "year={2012},"
                "}"
            ),
            "tags": ["implementation"],
        }
    ]

    def __init__(self, **inputs):
        super(FSLCommand, self).__init__(**inputs)
        self.inputs.on_trait_change(self._output_update, "output_type")

        if self._output_type is None:
            self._output_type = Info.output_type()

        if self.inputs.output_type is attrs.NOTHING:
            self.inputs.output_type = self._output_type
        else:
            self._output_update()

    def _output_update(self):
        self._output_type = self.inputs.output_type
        self.inputs.environ.update({"FSLOUTPUTTYPE": self.inputs.output_type})

    @classmethod
    def set_default_output_type(cls, output_type):
        """Set the default output type for FSL classes.

        This method is used to set the default output type for all fSL
        subclasses.  However, setting this will not update the output
        type for any existing instances.  For these, assign the
        <instance>.inputs.output_type.
        """

        if output_type in Info.ftypes:
            cls._output_type = output_type
        else:
            raise AttributeError("Invalid FSL output_type: %s" % output_type)

    @property
    def version(self):
        return Info.version()

    def _gen_fname(self, basename, cwd=None, suffix=None, change_ext=True, ext=None):
        """Generate a filename based on the given parameters.

        The filename will take the form: cwd/basename<suffix><ext>.
        If change_ext is True, it will use the extensions specified in
        <instance>inputs.output_type.

        Parameters
        ----------
        basename : str
            Filename to base the new filename on.
        cwd : str
            Path to prefix to the new filename. (default is os.getcwd())
        suffix : str
            Suffix to add to the `basename`.  (defaults is '' )
        change_ext : bool
            Flag to change the filename extension to the FSL output type.
            (default True)

        Returns
        -------
        fname : str
            New filename based on given parameters.

        """

        if basename == "":
            msg = "Unable to generate filename for command %s. " % self.cmd
            msg += "basename is not set!"
            raise ValueError(msg)
        if cwd is None:
            cwd = os.getcwd()
        if ext is None:
            ext = Info.output_type_to_ext(self.inputs.output_type)
        if change_ext:
            if suffix:
                suffix = "".join((suffix, ext))
            else:
                suffix = ext
        if suffix is None:
            suffix = ""
        fname = fname_presuffix(basename, suffix=suffix, use_ext=False, newpath=cwd)
        return fname

    def _overload_extension(self, value, name=None):
        return value + Info.output_type_to_ext(self.inputs.output_type)


def split_filename(fname):
    """Split a filename into parts: path, base filename and extension.

    Parameters
    ----------
    fname : str
        file or path name

    Returns
    -------
    pth : str
        base path from fname
    fname : str
        filename from fname, without extension
    ext : str
        file extension from fname

    Examples
    --------
    >>> from nipype.utils.filemanip import split_filename
    >>> pth, fname, ext = split_filename('/home/data/subject.nii.gz')
    >>> pth
    '/home/data'

    >>> fname
    'subject'

    >>> ext
    '.nii.gz'

    """

    special_extensions = [".nii.gz", ".tar.gz", ".niml.dset"]

    pth = op.dirname(fname)
    fname = op.basename(fname)

    ext = None
    for special_ext in special_extensions:
        ext_len = len(special_ext)
        if (len(fname) > ext_len) and (fname[-ext_len:].lower() == special_ext.lower()):
            ext = fname[-ext_len:]
            fname = fname[:-ext_len]
            break
    if not ext:
        fname, ext = op.splitext(fname)

    return pth, fname, ext


def on_cifs(fname):
    """
    Checks whether a file path is on a CIFS filesystem mounted in a POSIX
    host (i.e., has the ``mount`` command).

    On Windows, Docker mounts host directories into containers through CIFS
    shares, which has support for Minshall+French symlinks, or text files that
    the CIFS driver exposes to the OS as symlinks.
    We have found that under concurrent access to the filesystem, this feature
    can result in failures to create or read recently-created symlinks,
    leading to inconsistent behavior and ``FileNotFoundError``.

    This check is written to support disabling symlinks on CIFS shares.

    """
    # Only the first match (most recent parent) counts
    for fspath, fstype in _cifs_table:
        if fname.startswith(fspath):
            return fstype == "cifs"
    return False


def BibTeX(*args, **kwargs):
    """Perform no good and no bad"""
    pass


def _donothing_func(*args, **kwargs):
    """Perform no good and no bad"""
    pass


def which(cmd, env=None, pathext=None):
    """
    Return the path to an executable which would be run if the given
    cmd was called. If no cmd would be called, return ``None``.

    Code for Python < 3.3 is based on a code snippet from
    http://orip.org/2009/08/python-checking-if-executable-exists-in.html

    """

    if pathext is None:
        pathext = os.getenv("PATHEXT", "").split(os.pathsep)
        pathext.insert(0, "")

    path = os.getenv("PATH", os.defpath)
    if env and "PATH" in env:
        path = env.get("PATH")

    for ext in pathext:
        filename = shutil.which(cmd + ext, path=path)
        if filename:
            return filename
    return None


def fname_presuffix(fname, prefix="", suffix="", newpath=None, use_ext=True):
    """Manipulates path and name of input filename

    Parameters
    ----------
    fname : string
        A filename (may or may not include path)
    prefix : string
        Characters to prepend to the filename
    suffix : string
        Characters to append to the filename
    newpath : string
        Path to replace the path of the input fname
    use_ext : boolean
        If True (default), appends the extension of the original file
        to the output name.

    Returns
    -------
    Absolute path of the modified filename

    >>> from nipype.utils.filemanip import fname_presuffix
    >>> fname = 'foo.nii.gz'
    >>> fname_presuffix(fname,'pre','post','/tmp')
    '/tmp/prefoopost.nii.gz'

    >>> from nipype.interfaces.base import Undefined
    >>> fname_presuffix(fname, 'pre', 'post', Undefined) == \
            fname_presuffix(fname, 'pre', 'post')
    True

    """
    pth, fname, ext = split_filename(fname)
    if not use_ext:
        ext = ""

    # No need for isdefined: bool(Undefined) evaluates to False
    if newpath:
        pth = op.abspath(newpath)
    return op.join(pth, prefix + fname + suffix + ext)


def copyfile(
    originalfile,
    newfile,
    copy=False,
    create_new=False,
    hashmethod=None,
    use_hardlink=False,
    copy_related_files=True,
):
    """Copy or link ``originalfile`` to ``newfile``.

    If ``use_hardlink`` is True, and the file can be hard-linked, then a
    link is created, instead of copying the file.

    If a hard link is not created and ``copy`` is False, then a symbolic
    link is created.

    Parameters
    ----------
    originalfile : str
        full path to original file
    newfile : str
        full path to new file
    copy : Bool
        specifies whether to copy or symlink files
        (default=False) but only for POSIX systems
    use_hardlink : Bool
        specifies whether to hard-link files, when able
        (Default=False), taking precedence over copy
    copy_related_files : Bool
        specifies whether to also operate on related files, as defined in
        ``related_filetype_sets``

    Returns
    -------
    None

    """
    newhash = None
    orighash = None
    fmlogger.debug(newfile)

    if create_new:
        while op.exists(newfile):
            base, fname, ext = split_filename(newfile)
            s = re.search("_c[0-9]{4,4}$", fname)
            i = 0
            if s:
                i = int(s.group()[2:]) + 1
                fname = fname[:-6] + "_c%04d" % i
            else:
                fname += "_c%04d" % i
            newfile = base + os.sep + fname + ext

    if hashmethod is None:
        hashmethod = config.get("execution", "hash_method").lower()

    # Don't try creating symlinks on CIFS
    if copy is False and on_cifs(newfile):
        copy = True

    # Existing file
    # -------------
    # Options:
    #   symlink
    #       to regular file originalfile            (keep if symlinking)
    #       to same dest as symlink originalfile    (keep if symlinking)
    #       to other file                           (unlink)
    #   regular file
    #       hard link to originalfile               (keep)
    #       copy of file (same hash)                (keep)
    #       different file (diff hash)              (unlink)
    keep = False
    if op.lexists(newfile):
        if op.islink(newfile):
            if all(
                (
                    os.readlink(newfile) == op.realpath(originalfile),
                    not use_hardlink,
                    not copy,
                )
            ):
                keep = True
        elif posixpath.samefile(newfile, originalfile):
            keep = True
        else:
            if hashmethod == "timestamp":
                hashfn = hash_timestamp
            elif hashmethod == "content":
                hashfn = hash_infile
            else:
                raise AttributeError("Unknown hash method found:", hashmethod)
            newhash = hashfn(newfile)
            fmlogger.debug(
                "File: %s already exists,%s, copy:%d", newfile, newhash, copy
            )
            orighash = hashfn(originalfile)
            keep = newhash == orighash
        if keep:
            fmlogger.debug(
                "File: %s already exists, not overwriting, copy:%d", newfile, copy
            )
        else:
            os.unlink(newfile)

    # New file
    # --------
    # use_hardlink & can_hardlink => hardlink
    # ~hardlink & ~copy & can_symlink => symlink
    # ~hardlink & ~symlink => copy
    if not keep and use_hardlink:
        try:
            fmlogger.debug("Linking File: %s->%s", newfile, originalfile)
            # Use realpath to avoid hardlinking symlinks
            os.link(op.realpath(originalfile), newfile)
        except OSError:
            use_hardlink = False  # Disable hardlink for associated files
        else:
            keep = True

    if not keep and not copy and os.name == "posix":
        try:
            fmlogger.debug("Symlinking File: %s->%s", newfile, originalfile)
            os.symlink(originalfile, newfile)
        except OSError:
            copy = True  # Disable symlink for associated files
        else:
            keep = True

    if not keep:
        try:
            fmlogger.debug("Copying File: %s->%s", newfile, originalfile)
            shutil.copyfile(originalfile, newfile)
        except shutil.Error as e:
            fmlogger.warning(str(e))

    # Associated files
    if copy_related_files:
        related_file_pairs = (
            get_related_files(f, include_this_file=False)
            for f in (originalfile, newfile)
        )
        for alt_ofile, alt_nfile in zip(*related_file_pairs):
            if op.exists(alt_ofile):
                copyfile(
                    alt_ofile,
                    alt_nfile,
                    copy,
                    hashmethod=hashmethod,
                    use_hardlink=use_hardlink,
                    copy_related_files=False,
                )

    return newfile


def _parse_mount_table(exit_code, output):
    """Parses the output of ``mount`` to produce (path, fs_type) pairs

    Separated from _generate_cifs_table to enable testing logic with real
    outputs
    """
    # Not POSIX
    if exit_code != 0:
        return []

    # Linux mount example:  sysfs on /sys type sysfs (rw,nosuid,nodev,noexec)
    #                          <PATH>^^^^      ^^^^^<FSTYPE>
    # OSX mount example:    /dev/disk2 on / (hfs, local, journaled)
    #                               <PATH>^  ^^^<FSTYPE>
    pattern = re.compile(r".*? on (/.*?) (?:type |\()([^\s,\)]+)")

    # Keep line and match for error reporting (match == None on failure)
    # Ignore empty lines
    matches = [(l, pattern.match(l)) for l in output.strip().splitlines() if l]

    # (path, fstype) tuples, sorted by path length (longest first)
    mount_info = sorted(
        (match.groups() for _, match in matches if match is not None),
        key=lambda x: len(x[0]),
        reverse=True,
    )
    cifs_paths = [path for path, fstype in mount_info if fstype.lower() == "cifs"]

    # Report failures as warnings
    for line, match in matches:
        if match is None:
            fmlogger.debug("Cannot parse mount line: '%s'", line)

    return [
        mount
        for mount in mount_info
        if any(mount[0].startswith(path) for path in cifs_paths)
    ]


def hash_timestamp(afile):
    """Computes md5 hash of the timestamp of a file"""
    md5hex = None
    if op.isfile(afile):
        md5obj = md5()
        stat = os.stat(afile)
        md5obj.update(str(stat.st_size).encode())
        md5obj.update(str(stat.st_mtime).encode())
        md5hex = md5obj.hexdigest()
    return md5hex


def _generate_cifs_table():
    """Construct a reverse-length-ordered list of mount points that
    fall under a CIFS mount.

    This precomputation allows efficient checking for whether a given path
    would be on a CIFS filesystem.

    On systems without a ``mount`` command, or with no CIFS mounts, returns an
    empty list.
    """
    exit_code, output = sp.getstatusoutput("mount")
    return _parse_mount_table(exit_code, output)


def hash_infile(afile, chunk_len=8192, crypto=hashlib.md5, raise_notfound=False):
    """
    Computes hash of a file using 'crypto' module

    >>> hash_infile('smri_ants_registration_settings.json')
    'f225785dfb0db9032aa5a0e4f2c730ad'

    >>> hash_infile('surf01.vtk')
    'fdf1cf359b4e346034372cdeb58f9a88'

    >>> hash_infile('spminfo')
    '0dc55e3888c98a182dab179b976dfffc'

    >>> hash_infile('fsl_motion_outliers_fd.txt')
    'defd1812c22405b1ee4431aac5bbdd73'


    """
    if not op.isfile(afile):
        if raise_notfound:
            raise RuntimeError('File "%s" not found.' % afile)
        return None

    crypto_obj = crypto()
    with open(afile, "rb") as fp:
        while True:
            data = fp.read(chunk_len)
            if not data:
                break
            crypto_obj.update(data)
    return crypto_obj.hexdigest()


def get_related_files(filename, include_this_file=True):
    """Returns a list of related files, as defined in
    ``related_filetype_sets``, for a filename. (e.g., Nifti-Pair, Analyze (SPM)
    and AFNI files).

    Parameters
    ----------
    filename : str
        File name to find related filetypes of.
    include_this_file : bool
        If true, output includes the input filename.
    """
    related_files = []
    path, name, this_type = split_filename(filename)
    for type_set in related_filetype_sets:
        if this_type in type_set:
            for related_type in type_set:
                if include_this_file or related_type != this_type:
                    related_files.append(op.join(path, name + related_type))
    if not len(related_files):
        related_files = [filename]
    return related_files


class ProbTrackXInputSpec(ProbTrackXBaseInputSpec):
    mode = traits.Enum(
        "simple",
        "two_mask_symm",
        "seedmask",
        desc=(
            "options: simple (single seed voxel), seedmask "
            "(mask of seed voxels), twomask_symm (two bet "
            "binary masks)"
        ),
        argstr="--mode=%s",
        genfile=True,
    )
    mask2 = File(
        exists=True,
        desc=("second bet binary mask (in diffusion space) in " "twomask_symm mode"),
        argstr="--mask2=%s",
    )
    mesh = File(
        exists=True,
        desc="Freesurfer-type surface descriptor (in ascii format)",
        argstr="--mesh=%s",
    )


class ProbTrackX(FSLCommand):
    """ Use FSL  probtrackx for tractography on bedpostx results

    Examples
    --------

    >>> from nipype.interfaces import fsl
    >>> pbx = fsl.ProbTrackX(samples_base_name='merged', mask='mask.nii', \
    seed='MASK_average_thal_right.nii', mode='seedmask', \
    xfm='trans.mat', n_samples=3, n_steps=10, force_dir=True, opd=True, \
    os2t=True, target_masks = ['targets_MASK1.nii', 'targets_MASK2.nii'], \
    thsamples='merged_thsamples.nii', fsamples='merged_fsamples.nii', \
    phsamples='merged_phsamples.nii', out_dir='.')
    >>> pbx.cmdline
    'probtrackx --forcedir -m mask.nii --mode=seedmask --nsamples=3 --nsteps=10 --opd --os2t --dir=. --samples=merged --seed=MASK_average_thal_right.nii --targetmasks=targets.txt --xfm=trans.mat'

    """

    _cmd = "probtrackx"
    input_spec = ProbTrackXInputSpec
    output_spec = ProbTrackXOutputSpec

    def __init__(self, **inputs):
        warnings.warn(
            ("Deprecated: Please use create_bedpostx_pipeline " "instead"),
            DeprecationWarning,
        )
        return super(ProbTrackX, self).__init__(**inputs)

    def _run_interface(self, runtime):
        for i in range(1, len(self.inputs.thsamples) + 1):
            _, _, ext = split_filename(self.inputs.thsamples[i - 1])
            copyfile(
                self.inputs.thsamples[i - 1],
                self.inputs.samples_base_name + "_th%dsamples" % i + ext,
                copy=False,
            )
            _, _, ext = split_filename(self.inputs.thsamples[i - 1])
            copyfile(
                self.inputs.phsamples[i - 1],
                self.inputs.samples_base_name + "_ph%dsamples" % i + ext,
                copy=False,
            )
            _, _, ext = split_filename(self.inputs.thsamples[i - 1])
            copyfile(
                self.inputs.fsamples[i - 1],
                self.inputs.samples_base_name + "_f%dsamples" % i + ext,
                copy=False,
            )

        if self.inputs.target_masks is not attrs.NOTHING:
            f = open("targets.txt", "w")
            for target in self.inputs.target_masks:
                f.write("%s\n" % target)
            f.close()
        if isinstance(self.inputs.seed, list):
            f = open("seeds.txt", "w")
            for seed in self.inputs.seed:
                if isinstance(seed, list):
                    f.write("%s\n" % (" ".join([str(s) for s in seed])))
                else:
                    f.write("%s\n" % seed)
            f.close()

        runtime = super(ProbTrackX, self)._run_interface(runtime)
        if runtime.stderr:
            self.raise_exception(runtime)
        return runtime

    def _format_arg(self, name, spec, value):
        if name == "target_masks" and value is not attrs.NOTHING:
            fname = "targets.txt"
            return super(ProbTrackX, self)._format_arg(name, spec, [fname])
        elif name == "seed" and isinstance(value, list):
            fname = "seeds.txt"
            return super(ProbTrackX, self)._format_arg(name, spec, fname)
        else:
            return super(ProbTrackX, self)._format_arg(name, spec, value)

    def _list_outputs(self):
        outputs = self.output_spec().get()
        if self.inputs.out_dir is attrs.NOTHING:
            out_dir = self._gen_filename("out_dir")
        else:
            out_dir = self.inputs.out_dir

        outputs["log"] = os.path.abspath(os.path.join(out_dir, "probtrackx.log"))
        # outputs['way_total'] = os.path.abspath(os.path.join(out_dir,
        #                                                    'waytotal'))
        if isdefined(self.inputs.opd is True):
            if isinstance(self.inputs.seed, list) and isinstance(
                self.inputs.seed[0], list
            ):
                outputs["fdt_paths"] = []
                for seed in self.inputs.seed:
                    outputs["fdt_paths"].append(
                        os.path.abspath(
                            self._gen_fname(
                                ("fdt_paths_%s" % ("_".join([str(s) for s in seed]))),
                                cwd=out_dir,
                                suffix="",
                            )
                        )
                    )
            else:
                outputs["fdt_paths"] = os.path.abspath(
                    self._gen_fname("fdt_paths", cwd=out_dir, suffix="")
                )

        # handle seeds-to-target output files
        if self.inputs.target_masks is not attrs.NOTHING:
            outputs["targets"] = []
            for target in self.inputs.target_masks:
                outputs["targets"].append(
                    os.path.abspath(
                        self._gen_fname(
                            "seeds_to_" + os.path.split(target)[1],
                            cwd=out_dir,
                            suffix="",
                        )
                    )
                )
        if self.inputs.verbose is not attrs.NOTHING and self.inputs.verbose == 2:
            outputs["particle_files"] = [
                os.path.abspath(os.path.join(out_dir, "particle%d" % i))
                for i in range(self.inputs.n_samples)
            ]
        return outputs

    def _gen_filename(self, name):
        if name == "out_dir":
            return os.getcwd()
        elif name == "mode":
            if isinstance(self.inputs.seed, list) and isinstance(
                self.inputs.seed[0], list
            ):
                return "simple"
            else:
                return "seedmask"


class ProbTrackXOutputSpec(TraitedSpec):
    log = File(
        exists=True, desc="path/name of a text record of the command that was run"
    )
    fdt_paths = OutputMultiPath(
        File(exists=True),
        desc=(
            "path/name of a 3D image file "
            "containing the output connectivity "
            "distribution to the seed mask"
        ),
    )
    way_total = File(
        exists=True,
        desc=(
            "path/name of a text file containing a single "
            "number corresponding to the total number of "
            "generated tracts that have not been rejected by "
            "inclusion/exclusion mask criteria"
        ),
    )
    targets = traits.List(
        File(exists=True), desc=("a list with all generated seeds_to_target " "files")
    )
    particle_files = traits.List(
        File(exists=True),
        desc=(
            "Files describing all of the tract "
            "samples. Generated only if verbose is "
            "set to 2"
        ),
    )


class ProbTrackXBaseInputSpec(FSLCommandInputSpec):
    thsamples = InputMultiPath(File(exists=True), mandatory=True)
    phsamples = InputMultiPath(File(exists=True), mandatory=True)
    fsamples = InputMultiPath(File(exists=True), mandatory=True)
    samples_base_name = traits.Str(
        "merged",
        desc=("the rootname/base_name for samples " "files"),
        argstr="--samples=%s",
        usedefault=True,
    )
    mask = File(
        exists=True,
        desc="bet binary mask file in diffusion space",
        argstr="-m %s",
        mandatory=True,
    )
    seed = traits.Either(
        File(exists=True),
        traits.List(File(exists=True)),
        traits.List(traits.List(traits.Int(), minlen=3, maxlen=3)),
        desc=("seed volume(s), or voxel(s) or freesurfer " "label file"),
        argstr="--seed=%s",
        mandatory=True,
    )
    target_masks = InputMultiPath(
        File(exits=True),
        desc=("list of target masks - required for " "seeds_to_targets classification"),
        argstr="--targetmasks=%s",
    )
    waypoints = File(
        exists=True,
        desc=(
            "waypoint mask or ascii list of waypoint masks - "
            "only keep paths going through ALL the masks"
        ),
        argstr="--waypoints=%s",
    )
    network = traits.Bool(
        desc=(
            "activate network mode - only keep paths "
            "going through at least one seed mask "
            "(required if multiple seed masks)"
        ),
        argstr="--network",
    )
    seed_ref = File(
        exists=True,
        desc=(
            "reference vol to define seed space in simple mode "
            "- diffusion space assumed if absent"
        ),
        argstr="--seedref=%s",
    )
    out_dir = Directory(
        exists=True,
        argstr="--dir=%s",
        desc="directory to put the final volumes in",
        genfile=True,
    )
    force_dir = traits.Bool(
        True,
        desc=(
            "use the actual directory name given - i.e. "
            "do not add + to make a new directory"
        ),
        argstr="--forcedir",
        usedefault=True,
    )
    opd = traits.Bool(
        True, desc="outputs path distributions", argstr="--opd", usedefault=True
    )
    correct_path_distribution = traits.Bool(
        desc=("correct path distribution " "for the length of the " "pathways"),
        argstr="--pd",
    )
    os2t = traits.Bool(desc="Outputs seeds to targets", argstr="--os2t")
    # paths_file = File('nipype_fdtpaths', usedefault=True, argstr='--out=%s',
    #                 desc='produces an output file (default is fdt_paths)')
    avoid_mp = File(
        exists=True,
        desc=("reject pathways passing through locations given by " "this mask"),
        argstr="--avoid=%s",
    )
    stop_mask = File(
        exists=True,
        argstr="--stop=%s",
        desc="stop tracking at locations given by this mask file",
    )
    xfm = File(
        exists=True,
        argstr="--xfm=%s",
        desc=(
            "transformation matrix taking seed space to DTI space "
            "(either FLIRT matrix or FNIRT warp_field) - default is "
            "identity"
        ),
    )
    inv_xfm = File(
        argstr="--invxfm=%s",
        desc=(
            "transformation matrix taking DTI space to seed "
            "space (compulsory when using a warp_field for "
            "seeds_to_dti)"
        ),
    )
    n_samples = traits.Int(
        5000,
        argstr="--nsamples=%d",
        desc="number of samples - default=5000",
        usedefault=True,
    )
    n_steps = traits.Int(
        argstr="--nsteps=%d", desc="number of steps per sample - default=2000"
    )
    dist_thresh = traits.Float(
        argstr="--distthresh=%.3f",
        desc=("discards samples shorter than this " "threshold (in mm - default=0)"),
    )
    c_thresh = traits.Float(
        argstr="--cthr=%.3f", desc="curvature threshold - default=0.2"
    )
    sample_random_points = traits.Bool(
        argstr="--sampvox", desc=("sample random points within " "seed voxels")
    )
    step_length = traits.Float(
        argstr="--steplength=%.3f", desc="step_length in mm - default=0.5"
    )
    loop_check = traits.Bool(
        argstr="--loopcheck",
        desc=(
            "perform loop_checks on paths - slower, "
            "but allows lower curvature threshold"
        ),
    )
    use_anisotropy = traits.Bool(
        argstr="--usef", desc="use anisotropy to constrain tracking"
    )
    rand_fib = traits.Enum(
        0,
        1,
        2,
        3,
        argstr="--randfib=%d",
        desc=(
            "options: 0 - default, 1 - to randomly "
            "sample initial fibres (with f > fibthresh), "
            "2 - to sample in proportion fibres (with "
            "f>fibthresh) to f, 3 - to sample ALL "
            "populations at random (even if "
            "f<fibthresh)"
        ),
    )
    fibst = traits.Int(
        argstr="--fibst=%d",
        desc=(
            "force a starting fibre for tracking - "
            "default=1, i.e. first fibre orientation. Only "
            "works if randfib==0"
        ),
    )
    mod_euler = traits.Bool(argstr="--modeuler", desc="use modified euler streamlining")
    random_seed = traits.Bool(argstr="--rseed", desc="random seed")
    s2tastext = traits.Bool(
        argstr="--s2tastext",
        desc=(
            "output seed-to-target counts as a text "
            "file (useful when seeding from a mesh)"
        ),
    )
    verbose = traits.Enum(
        0,
        1,
        2,
        desc=("Verbose level, [0-2]. Level 2 is required to " "output particle files."),
        argstr="--verbose=%d",
    )


class ProbTrackX2OutputSpec(ProbTrackXOutputSpec):
    network_matrix = File(
        exists=True, desc=("the network matrix generated by --omatrix1 " "option")
    )
    matrix1_dot = File(exists=True, desc="Output matrix1.dot - SeedToSeed Connectivity")
    lookup_tractspace = File(
        exists=True, desc=("lookup_tractspace generated by " "--omatrix2 option")
    )
    matrix2_dot = File(exists=True, desc="Output matrix2.dot - SeedToLowResMask")
    matrix3_dot = File(exists=True, desc="Output matrix3 - NxN connectivity matrix")


class ProbTrackX2InputSpec(ProbTrackXBaseInputSpec):
    simple = traits.Bool(
        desc=(
            "rack from a list of voxels (seed must be a " "ASCII list of coordinates)"
        ),
        argstr="--simple",
    )
    fopd = File(
        exists=True,
        desc="Other mask for binning tract distribution",
        argstr="--fopd=%s",
    )
    waycond = traits.Enum(
        "OR",
        "AND",
        argstr="--waycond=%s",
        desc=('Waypoint condition. Either "AND" (default) ' 'or "OR"'),
    )
    wayorder = traits.Bool(
        desc=(
            "Reject streamlines that do not hit "
            "waypoints in given order. Only valid if "
            "waycond=AND"
        ),
        argstr="--wayorder",
    )
    onewaycondition = traits.Bool(
        desc=("Apply waypoint conditions to each " "half tract separately"),
        argstr="--onewaycondition",
    )
    omatrix1 = traits.Bool(
        desc="Output matrix1 - SeedToSeed Connectivity", argstr="--omatrix1"
    )
    distthresh1 = traits.Float(
        argstr="--distthresh1=%.3f",
        desc=(
            "Discards samples (in matrix1) shorter "
            "than this threshold (in mm - "
            "default=0)"
        ),
    )
    omatrix2 = traits.Bool(
        desc="Output matrix2 - SeedToLowResMask",
        argstr="--omatrix2",
        requires=["target2"],
    )
    target2 = File(
        exists=True,
        desc=(
            "Low resolution binary brain mask for storing "
            "connectivity distribution in matrix2 mode"
        ),
        argstr="--target2=%s",
    )
    omatrix3 = traits.Bool(
        desc="Output matrix3 (NxN connectivity matrix)",
        argstr="--omatrix3",
        requires=["target3", "lrtarget3"],
    )
    target3 = File(
        exists=True,
        desc=("Mask used for NxN connectivity matrix (or Nxn if " "lrtarget3 is set)"),
        argstr="--target3=%s",
    )
    lrtarget3 = File(
        exists=True,
        desc="Column-space mask used for Nxn connectivity matrix",
        argstr="--lrtarget3=%s",
    )
    distthresh3 = traits.Float(
        argstr="--distthresh3=%.3f",
        desc=(
            "Discards samples (in matrix3) shorter "
            "than this threshold (in mm - "
            "default=0)"
        ),
    )
    omatrix4 = traits.Bool(
        desc=("Output matrix4 - DtiMaskToSeed (special " "Oxford Sparse Format)"),
        argstr="--omatrix4",
    )
    colmask4 = File(
        exists=True,
        desc="Mask for columns of matrix4 (default=seed mask)",
        argstr="--colmask4=%s",
    )
    target4 = File(exists=True, desc="Brain mask in DTI space", argstr="--target4=%s")
    meshspace = traits.Enum(
        "caret",
        "freesurfer",
        "first",
        "vox",
        argstr="--meshspace=%s",
        desc=(
            'Mesh reference space - either "caret" '
            '(default) or "freesurfer" or "first" or '
            '"vox"'
        ),
    )


class ProbTrackX2(ProbTrackX):
    """Use FSL  probtrackx2 for tractography on bedpostx results

    Examples
    --------

    >>> from nipype.interfaces import fsl
    >>> pbx2 = fsl.ProbTrackX2()
    >>> pbx2.inputs.seed = 'seed_source.nii.gz'
    >>> pbx2.inputs.thsamples = 'merged_th1samples.nii.gz'
    >>> pbx2.inputs.fsamples = 'merged_f1samples.nii.gz'
    >>> pbx2.inputs.phsamples = 'merged_ph1samples.nii.gz'
    >>> pbx2.inputs.mask = 'nodif_brain_mask.nii.gz'
    >>> pbx2.inputs.out_dir = '.'
    >>> pbx2.inputs.n_samples = 3
    >>> pbx2.inputs.n_steps = 10
    >>> pbx2.cmdline
    'probtrackx2 --forcedir -m nodif_brain_mask.nii.gz --nsamples=3 --nsteps=10 --opd --dir=. --samples=merged --seed=seed_source.nii.gz'
    """

    _cmd = "probtrackx2"
    input_spec = ProbTrackX2InputSpec
    output_spec = ProbTrackX2OutputSpec

    def _list_outputs(self):
        outputs = super(ProbTrackX2, self)._list_outputs()

        if self.inputs.out_dir is attrs.NOTHING:
            out_dir = os.getcwd()
        else:
            out_dir = self.inputs.out_dir

        outputs["way_total"] = os.path.abspath(os.path.join(out_dir, "waytotal"))

        if self.inputs.omatrix1 is not attrs.NOTHING:
            outputs["network_matrix"] = os.path.abspath(
                os.path.join(out_dir, "matrix_seeds_to_all_targets")
            )
            outputs["matrix1_dot"] = os.path.abspath(
                os.path.join(out_dir, "fdt_matrix1.dot")
            )

        if self.inputs.omatrix2 is not attrs.NOTHING:
            outputs["lookup_tractspace"] = os.path.abspath(
                os.path.join(out_dir, "lookup_tractspace_fdt_matrix2.nii.gz")
            )
            outputs["matrix2_dot"] = os.path.abspath(
                os.path.join(out_dir, "fdt_matrix2.dot")
            )

        if self.inputs.omatrix3 is not attrs.NOTHING:
            outputs["matrix3_dot"] = os.path.abspath(
                os.path.join(out_dir, "fdt_matrix3.dot")
            )
        return outputs


def _gen_filename(name, inputs=None, stdout=None, stderr=None, output_dir=None):
    if name == "out_dir":
        return output_dir
    elif name == "mode":
        if isinstance(inputs.seed, list) and isinstance(inputs.seed[0], list):
            return "simple"
        else:
            return "seedmask"


def _list_outputs(inputs=None, stdout=None, stderr=None, output_dir=None):
    outputs = super(ProbTrackX2, self)._list_outputs()

    if inputs.out_dir is attrs.NOTHING:
        out_dir = output_dir
    else:
        out_dir = inputs.out_dir

    outputs["way_total"] = os.path.abspath(os.path.join(out_dir, "waytotal"))

    if inputs.omatrix1 is not attrs.NOTHING:
        outputs["network_matrix"] = os.path.abspath(
            os.path.join(out_dir, "matrix_seeds_to_all_targets")
        )
        outputs["matrix1_dot"] = os.path.abspath(
            os.path.join(out_dir, "fdt_matrix1.dot")
        )

    if inputs.omatrix2 is not attrs.NOTHING:
        outputs["lookup_tractspace"] = os.path.abspath(
            os.path.join(out_dir, "lookup_tractspace_fdt_matrix2.nii.gz")
        )
        outputs["matrix2_dot"] = os.path.abspath(
            os.path.join(out_dir, "fdt_matrix2.dot")
        )

    if inputs.omatrix3 is not attrs.NOTHING:
        outputs["matrix3_dot"] = os.path.abspath(
            os.path.join(out_dir, "fdt_matrix3.dot")
        )
    return outputs
