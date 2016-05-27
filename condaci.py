#!/usr/bin/env python
import subprocess
import os
import contextlib
import shutil
import os.path as p
from functools import partial
import platform as stdplatform
import uuid
import sys
from pprint import pprint


VS9_PY_VERS = ['2.7']
VS10_PY_VERS = ['3.3', '3.4']
VS14_PY_VERS = ['3.5']
SUPPORTED_PY_VERS = VS9_PY_VERS + VS10_PY_VERS + VS14_PY_VERS

SUPPORTED_ERR_MSG = 'FATAL: Python version not supported, must be one of {}'.format(
    SUPPORTED_PY_VERS)

PROGRAM_FILES = os.environ.get('PROGRAMFILES(x86)', os.environ.get('PROGRAMFILES', ''))
VS2008_PATH = os.path.join(PROGRAM_FILES, 'Microsoft Visual Studio 9.0')
VS2008_BIN_PATH = os.path.join(VS2008_PATH, 'VC', 'bin')
VS2010_PATH = os.path.join(PROGRAM_FILES, 'Microsoft Visual Studio 10.0')
VS2010_BIN_PATH = os.path.join(VS2010_PATH, 'VC', 'bin')
VS2010_AMD64_VCVARS_CMD = r'CALL "C:\Program Files\Microsoft SDKs\Windows\v7.1\Bin\SetEnv.cmd" /x64 /Release'

# a random string we can use for the miniconda installer
# (to avoid name collisions)
RANDOM_UUID = uuid.uuid4()

# -------------------------------- STATE ------------------------------------ #

# Key globals that need to be set for the rest of the script.
PYTHON_VERSION = None
PYTHON_VERSION_NO_DOT = None
BINSTAR_USER = None
BINSTAR_KEY = None
ARCH = None


def set_globals_from_environ(verbose=True):
    global PYTHON_VERSION, BINSTAR_KEY, BINSTAR_USER, PYTHON_VERSION_NO_DOT, ARCH

    if not (is_on_appveyor() or is_on_travis() or is_on_jenkins()):
        raise ValueError('FATAL: Unknown CI system.')

    PYTHON_VERSION = os.environ.get('PYTHON_VERSION')
    # ARCH or PLATFORM - PLATFORM on Appveyor
    if 'ARCH' in os.environ or 'PLATFORM' in os.environ:
        ARCH = os.environ.get('ARCH', os.environ.get('PLATFORM'))
        arch_origin = 'Environment'
    else:
        # If we weren't given the ARCH variable (as on Jenkins) then predict
        # the architecture from the Python version (x86 or x64)
        ARCH = python_arch()
        arch_origin = 'Python'
    BINSTAR_USER = os.environ.get('BINSTAR_USER')
    BINSTAR_KEY = os.environ.get('BINSTAR_KEY')

    if verbose:
        print('Environment variables extracted:')
        print('  PYTHON_VERSION: {}'.format(PYTHON_VERSION))
        print('  ARCH:           {} - ({})'.format(ARCH, arch_origin))
        print('  BINSTAR_USER:   {}'.format(BINSTAR_USER))
        print('  BINSTAR_KEY:    {}'.format('*****' if BINSTAR_KEY is not None
                                            else '-'))

    if PYTHON_VERSION is None:
        raise ValueError('FATAL: PYTHON_VERSION is not set.')
    if PYTHON_VERSION not in SUPPORTED_PY_VERS:
        raise ValueError("FATAL: PYTHON_VERSION '{}' is invalid - must be "
                         "one of {}".format(PYTHON_VERSION, SUPPORTED_PY_VERS))
    if ARCH is None:
        raise ValueError('FATAL: ARCH is not set.')

    # Required when setting Python version in conda
    PYTHON_VERSION_NO_DOT = PYTHON_VERSION.replace('.', '')


# ------------------------------ UTILITIES ---------------------------------- #


class FakeSink(object):

    def write(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass


@contextlib.contextmanager
def suppress_stdout():
    cached_stdout = sys.stdout
    sys.stdout = FakeSink()
    yield
    sys.stdout = cached_stdout


# forward stderr to stdout
check = partial(subprocess.check_call, stderr=subprocess.STDOUT)


def execute(cmd, verbose=True, env_additions=None):
    r""" Runs a command, printing the command and it's output to screen.
    """
    env_for_p = os.environ.copy()
    if env_additions is not None:
        env_for_p.update(env_additions)
    if verbose:
        print('> {}'.format(' '.join(cmd)))
        if env_additions is not None:
            print('Additional environment variables: '
                  '{}'.format(', '.join(['{}={}'.format(k, v)
                                         for k, v in env_additions.items()])))
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, env=env_for_p)
    sentinel = ''
    if sys.version_info.major == 3:
        sentinel = b''
    for line in iter(proc.stdout.readline, sentinel):
        if verbose:
            if sys.version_info.major == 3:
                # convert bytes to string
                line = line.decode("utf-8")
            sys.stdout.write(line)
            sys.stdout.flush()
    output = proc.communicate()[0]
    if proc.returncode == 0:
        return
    else:
        e = subprocess.CalledProcessError(proc.returncode, cmd, output=output)
        print(' -> {}'.format(e.output))
        raise e


def execute_sequence(*cmds, **kwargs):
    r""" Execute a sequence of commands. If any fails, display an error.
    """
    verbose = kwargs.get('verbose', True)
    for cmd in cmds:
        execute(cmd, verbose)


def download_file(url, path_to_download):
    try:
        from urllib2 import urlopen
    except ImportError:
        from urllib.request import urlopen
    f = urlopen(url)
    with open(path_to_download, "wb") as fp:
        fp.write(f.read())
    fp.close()


def dirs_containing_file(fname, root=os.curdir):
    for path, dirs, files in os.walk(os.path.abspath(root)):
        if fname in files:
            yield path


def host_platform():
    return stdplatform.system()


def is_windows():
    return host_platform() == 'Windows'


def python_arch():
    # We care about the Python architecture, not the OS.
    return 'x64' if sys.maxsize > 2**32 else 'x86'


# ------------------------ MINICONDA INTEGRATION ---------------------------- #

def url_for_platform_version(platform, arch):
    # Always install Miniconda3
    version = 'latest'
    base_url = 'http://repo.continuum.io/miniconda/Miniconda3'
    platform_str = {'Linux': 'Linux',
                    'Darwin': 'MacOSX',
                    'Windows': 'Windows'}
    arch_str = {'x64': 'x86_64',
                'x86': 'x86'}
    ext = {'Linux': '.sh',
           'Darwin': '.sh',
           'Windows': '.exe'}

    return '-'.join([base_url, version,
                     platform_str[platform],
                     arch_str[arch]]) + ext[platform]


def appveyor_miniconda_dir():
    # We always prefer the Miniconda3 version
    conda_dir = r'C:\Miniconda3'

    if ARCH == 'x64':
        conda_dir += '-x64'

    return conda_dir


def travis_miniconda_dir():
    return p.expanduser('~/miniconda')


def jenkins_unix_miniconda_dir():
    return p.expanduser('~/miniconda')


def jenkins_windows_miniconda_dir():
    return r'C:\miniconda'


def temp_installer_path():
    # we need a place to download the miniconda installer to. use a random
    # string for the filename to avoid collisions, but choose the dir based
    # on platform
    return ('C:\{}.exe'.format(RANDOM_UUID) if is_windows()
            else p.expanduser('~/{}.sh'.format(RANDOM_UUID)))


def miniconda_dir():
    # the directory where miniconda will be installed to/is
    if is_on_appveyor():
        path = appveyor_miniconda_dir()
    elif is_on_travis():
        path = travis_miniconda_dir()
    elif is_on_jenkins():
        if is_windows():
            path = jenkins_windows_miniconda_dir()
        else:
            path = jenkins_unix_miniconda_dir()

        # Jenkins persists miniconda installs between builds, but we want a
        # unique miniconda env for each executor. Therefore, on jenkins
        # the miniconda paths look like
        # {MINICONDA_DIR}/{EXECUTOR_NUMBER}/{ARCH}
        if not os.path.isdir(path):
            os.mkdir(path)
        exec_no = os.environ['EXECUTOR_NUMBER']
        j_path = os.path.join(path, exec_no)
        if not os.path.isdir(j_path):
            os.mkdir(j_path)
        path = os.path.join(j_path, ARCH)
    return path


# the script directory inside a miniconda install varies based on platform
def miniconda_script_dir_name():
    return 'Scripts' if is_windows() else 'bin'


# handles to binaries from a miniconda install
exec_ext = '.exe' if is_windows() else ''
miniconda_script_dir = lambda mc: p.join(mc, miniconda_script_dir_name())
conda = lambda mc: p.join(miniconda_script_dir(mc), 'conda' + exec_ext)
binstar = lambda mc: p.join(miniconda_script_dir(mc), 'anaconda' + exec_ext)


def acquire_miniconda(url, path_to_download):
    print('Downloading miniconda from {} to {}'.format(url, path_to_download))
    download_file(url, path_to_download)


def install_miniconda(path_to_installer, path_to_install):
    print('Installing miniconda to {}'.format(path_to_install))
    if is_windows():
        execute([path_to_installer, '/InstallationType=AllUsers',
                 '/AddToPath=0', '/RegisterPath=1', '/NoRegistry=1',
                 '/S', '/D={}'.format(path_to_install)])
    else:
        execute(['chmod', '+x', path_to_installer])
        execute([path_to_installer, '-b', '-p', path_to_install])


def setup_miniconda(installation_path, binstar_user=None):
    conda_cmd = conda(installation_path)
    if os.path.exists(conda_cmd):
        print('conda is already setup at {}'.format(installation_path))
    else:
        print('No existing conda install detected at {}'.format(installation_path))
        url = url_for_platform_version(host_platform(), ARCH)
        print('Setting up miniconda from URL {}'.format(url))
        print("(Installing to '{}')".format(installation_path))
        acquire_miniconda(url, temp_installer_path())
        install_miniconda(temp_installer_path(), installation_path)
        # delete the installer now we are done
        os.unlink(temp_installer_path())
    cmds = [[conda_cmd, 'update', '-q', '--yes', 'conda'],
            [conda_cmd, 'install', '-q', '--yes', 'conda-build', 'jinja2',
             'anaconda-client']]
    root_config = os.path.join(installation_path, '.condarc')
    if os.path.exists(root_config):
        print('existing root config at present at {} - removing'.format(root_config))
        os.unlink(root_config)
    if binstar_user is not None:
        print("(adding user channel '{}' for dependencies to root config)".format(binstar_user))
        cmds.append([conda_cmd, 'config', '--system', '--add', 'channels', binstar_user])
    else:
        print('No user channels have been configured (all dependencies have to '
              'be sourced from anaconda)')
    execute_sequence(*cmds)


# ------------------------ CONDA BUILD INTEGRATION -------------------------- #

def get_conda_build_path(recipe_dir):
    try:
        from conda_build.metadata import MetaData
        from conda_build.build import bldpkg_path
        m = MetaData(recipe_dir)
        return bldpkg_path(m).strip()
    except:
        raise ValueError('Unable to find recipe_dir')


def windows_setup_compiler():
    if PYTHON_VERSION in VS9_PY_VERS and ARCH == 'x64':
        VS2008_AMD64_PATH = os.path.join(VS2008_BIN_PATH, 'amd64')
        if not os.path.exists(VS2008_AMD64_PATH):
            os.makedirs(VS2008_AMD64_PATH)
        VCVARS64_PATH = os.path.join(VS2008_BIN_PATH, 'vcvars64.bat')
        VCVARSAMD64_PATH = os.path.join(VS2008_AMD64_PATH, 'vcvarsamd64.bat')
        if not os.path.exists(VCVARS64_PATH):
            print("Unable to find '{}' - skipping fix for VS2008 64-bit.".format(
                VCVARS64_PATH))
        else:
            print("Copying '{}' to '{}' to fix VS2008 64-bit configuration.".format(
                      VCVARS64_PATH, VCVARSAMD64_PATH))
            shutil.copyfile(VCVARS64_PATH, VCVARSAMD64_PATH)
    # Python 3.3 or 3.4
    elif PYTHON_VERSION in VS10_PY_VERS and ARCH == 'x64':
        VS2010_AMD64_PATH = os.path.join(VS2010_BIN_PATH, 'amd64')
        if not os.path.exists(VS2010_AMD64_PATH):
            os.makedirs(VS2010_AMD64_PATH)
        VS2010_AMD64_VCVARS_PATH = os.path.join(VS2010_AMD64_PATH,
                                                'vcvars64.bat')
        print("Writing '{}' to '{}' to fix VS2010 64-bit configuration.".format(
            VS2010_AMD64_VCVARS_CMD, VS2010_AMD64_VCVARS_PATH))
        with open(VS2010_AMD64_VCVARS_PATH, 'w') as f:
            f.write(VS2010_AMD64_VCVARS_CMD)


def build_conda_package(mc, path, binstar_user=None):
    print('Building package at path {}'.format(path))
    v = get_version(path)
    print('Detected version: {}'.format(v))
    print('Setting CONDACI_VERSION environment variable to {}'.format(v))
    os.environ['CONDACI_VERSION'] = v
    print('Setting CONDA_PY environment variable to {}'.format(
        PYTHON_VERSION_NO_DOT))
    os.environ['CONDA_PY'] = PYTHON_VERSION_NO_DOT

    # we want to add the master channel when doing dev builds to source our
    # other dev dependencies
    if not (is_release_tag(v) or is_rc_tag(v)):
        print('building a non-release non-RC build - adding master channel.')
        if binstar_user is None:
            print('warning - no binstar user provided - cannot add master channel')
        else:
            execute([conda(mc), 'config', '--system', '--add', 'channels',
                     binstar_user + '/channel/master'])
    else:
        print('building a RC or tag release - no master channel added.')

    if 'BINSTAR_KEY' in os.environ:
        print('found BINSTAR_KEY in environment - deleting to '
              'prevent from leaking.')
        del os.environ['BINSTAR_KEY']

    if is_windows():
        # Before building the package, we may need to edit the environment a bit
        # to handle the nightmare that is Visual Studio compilation
        windows_setup_compiler()
    execute([conda(mc), 'build', '-q', path,
             '--py={}'.format(PYTHON_VERSION_NO_DOT)])


# ------------------------- VERSIONING INTEGRATION -------------------------- #

# versions that match up to master changes (anything after a '+')
same_version_different_build = lambda v1, v2: v2.startswith(v1.split('+')[0])


def versions_from_versioneer():
    # Ideally, we will interrogate versioneer to find out the version of the
    # project we are building. Note that we can't simply look at
    # project.__version__ as we need the version string pre-build, so the
    # package may not be importable.
    for dir_ in dirs_containing_file('_version.py'):
        sys.path.insert(0, dir_)

        try:
            import _version
            yield _version.get_versions()['version']
        except Exception as e:
            print(e)
        finally:
            if '_version' in sys.modules:
                sys.modules.pop('_version')

            sys.path.pop(0)


def version_from_meta_yaml(path):
    meta_yaml_path = os.path.join(path, 'meta.yaml')
    with open(meta_yaml_path, 'rt') as f:
        s = f.read()
    v = s.split('version:', 1)[1].split('\n', 1)[0].strip().strip("'").strip('"')
    if '{{' in v:
        raise ValueError('Trying to establish version from meta.yaml'
                         ' and it seems to be dynamic: {}'.format(v))
    return v


def get_version(path):
    # search for versioneer versions in our subdirs
    versions = list(versions_from_versioneer())

    if len(versions) == 1:
        version = versions[0]
        print('Found unambiguous versioneer version: {}'.format(version))
    elif len(versions) > 1:
        raise ValueError('Multiple versioneer _version.py files - cannot '
                         'resolve unambiguous version. '
                         'Versions found are: {}'.format(versions))
    else:
        # this project doesn't seem to be versioneer controlled - maybe the
        # version is hardcoded? Interrogate meta.yaml
        version = version_from_meta_yaml(path)
    return version

# booleans about the state of the the PEP440 tags.
is_tag = lambda v: '+' not in v
is_dev_tag = lambda v: v.split('.')[-1].startswith('dev')
is_rc_tag = lambda v: 'rc' in v.split('+')[0]
is_release_tag = lambda v: is_tag(v) and not (is_rc_tag(v) or is_dev_tag(v))


# -------------------------- BINSTAR INTEGRATION ---------------------------- #


class LetMeIn:
    def __init__(self, key):
        self.token = key
        self.site = False


def login_to_binstar():
    from binstar_client.utils import get_binstar
    return get_binstar()


def login_to_binstar_with_key(key):
    from binstar_client.utils import get_binstar
    return get_binstar(args=LetMeIn(key))


class BinstarFile(object):

    def __init__(self, full_name):
        self.full_name = full_name

    @property
    def user(self):
        return self.full_name.split('/')[0]

    @property
    def name(self):
        return self.full_name.split('/')[1]

    @property
    def basename(self):
        return '/'.join(self.full_name.split('/')[3:])

    @property
    def version(self):
        return self.full_name.split('/')[2]

    @property
    def platform(self):
        return self.full_name.replace('\\', '/').split('/')[3]

    @property
    def configuration(self):
        return self.full_name.replace('\\', '/').split('/')[4].split('-')[2].split('.')[0]

    def __str__(self):
        return self.full_name

    def __repr__(self):
        return self.full_name

    def all_info(self):
        s = ["         user: {}".format(self.user),
             "         name: {}".format(self.name),
             "     basename: {}".format(self.basename),
             "      version: {}".format(self.version),
             "     platform: {}".format(self.platform),
             "configuration: {}".format(self.configuration)]
        return "\n".join(s)


configuration_from_binstar_filename = lambda fn: fn.split('-')[-1].split('.')[0]
name_from_binstar_filename = lambda fn: fn.split('-')[0]
version_from_binstar_filename = lambda fn: fn.split('-')[1]
platform_from_binstar_filepath = lambda fp: p.split(p.split(fp)[0])[-1]


def binstar_channels_for_user(b, user):
    return b.list_channels(user).keys()


def binstar_files_on_channel(b, user, channel):
    info = b.show_channel(channel, user)
    return [BinstarFile(i['full_name']) for i in info['files']]


def binstar_remove_file(b, bfile):
    b.remove_dist(bfile.user, bfile.name, bfile.version, bfile.basename)


def files_to_remove(b, user, channel, filepath):
    platform_ = platform_from_binstar_filepath(filepath)
    filename = p.split(filepath)[-1]
    name = name_from_binstar_filename(filename)
    version = version_from_binstar_filename(filename)
    configuration = configuration_from_binstar_filename(filename)
    # find all the files on this channel
    all_files = binstar_files_on_channel(b, user, channel)
    # other versions of this exact setup that are not tagged versions should
    # be removed
    print('Removing old releases matching:'
          '\nname: {}\nconfiguration: {}\nplatform: {}'
          '\nversion: {}'.format(name, configuration, platform_, version))
    print('candidate releases with same name are:')
    pprint([f.all_info() for f in all_files if f.name == name])
    return [f for f in all_files if
            f.name == name and
            f.configuration == configuration and
            f.platform == platform_ and
            f.version != version and
            not is_release_tag(f.version) and
            same_version_different_build(version, f.version)]


def purge_old_binstar_files(b, user, channel, filepath):
    to_remove = files_to_remove(b, user, channel, filepath)
    print("Found {} releases to remove".format(len(to_remove)))
    for old_file in to_remove:
        print("Removing '{}'".format(old_file))
        binstar_remove_file(b, old_file)


def binstar_upload_unchecked(mc, key, user, channel, path):
    print('Uploading from {} using {}'.format(path, binstar(mc)))
    try:
        # TODO - could this safely be co? then we would get the binstar error..
        check([binstar(mc), '-t', key, 'upload',
               '--force', '-u', user, '-c', channel, path])
    except subprocess.CalledProcessError as e:
        # mask the binstar key...
        cmd = e.cmd
        cmd[2] = 'BINSTAR_KEY'
        # ...then raise the error
        raise subprocess.CalledProcessError(e.returncode, cmd)


def binstar_upload_if_appropriate(mc, path, user, key):
    if key is None:
        print('No binstar key provided')
    if user is None:
        print('No binstar user provided')
    if user is None or key is None:
        print('-> Unable to upload to binstar')
        return
    print('Have a user ({}) and key - can upload if suitable'.format(user))

    # decide if we should attempt an upload (if it's a PR we can't)
    if resolve_can_upload_from_ci():
        print('Auto resolving channel based on release type and CI status')
        channel = binstar_channel_from_ci(path)
        print("Fit to upload to channel '{}'".format(channel))
        binstar_upload_and_purge(mc, key, user, channel,
                                 get_conda_build_path(path))
    else:
        print("Cannot upload to binstar - must be a PR.")


def binstar_upload_and_purge(mc, key, user, channel, filepath):
    if not os.path.exists(filepath):
        raise ValueError('Built file {} does not exist. '
                         'UPLOAD FAILED.'.format(filepath))
    else:
        print('Uploading to {}/{}'.format(user, channel))
        binstar_upload_unchecked(mc, key, user, channel, filepath)
        b = login_to_binstar_with_key(key)
        if channel != 'main':
            print("Purging old releases from channel '{}'".format(channel))
            purge_old_binstar_files(b, user, channel, filepath)
        else:
            print("On main channel - no purging of releases will be done.")


# -------------- CONTINUOUS INTEGRATION-SPECIFIC FUNCTIONALITY -------------- #

is_on_appveyor = lambda: 'APPVEYOR' in os.environ
is_on_travis = lambda: 'TRAVIS' in os.environ
is_on_jenkins = lambda: 'JENKINS_URL' in os.environ

is_pr_from_travis = lambda: os.environ['TRAVIS_PULL_REQUEST'] != 'false'
is_pr_from_appveyor = lambda: 'APPVEYOR_PULL_REQUEST_NUMBER' in os.environ
# TODO: Remove when ghprb is fixed
is_pr_from_jenkins = lambda: os.environ['JOB_NAME'].split('/')[0][-3:] == '-pr'

branch_from_appveyor = lambda: os.environ['APPVEYOR_REPO_BRANCH']


def branch_from_jenkins():
    branch = os.environ['GIT_BRANCH']
    print('Jenkins has set GIT_BRANCH={}'.format(branch))
    if branch.startswith('origin/tags/'):
        print('WARNING - on jenkins and GIT_BRANCH starts with origin/tags/. '
              'This suggests that we are building a tag.')
        print('Jenkins obscures the branch in this scenario, so we assume that'
              ' the branch is "master"')
        return 'master'
    elif branch.startswith('origin/'):
        return branch.split('origin/', 1)[-1]
    else:
        raise ValueError('Error: jenkins branch name seems '
                         'suspicious: {}'.format(branch))


def branch_from_travis():
    tag = os.environ['TRAVIS_TAG']
    branch = os.environ['TRAVIS_BRANCH']
    if tag == branch:
        print('WARNING - on travis and TRAVIS_TAG == TRAVIS_BRANCH. This '
              'suggests that we are building a tag.')
        print('Travis obscures the branch in this scenario, so we assume that'
              ' the branch is "master"')
        return 'master'
    else:
        return branch


def is_pr_on_ci():
    if is_on_travis():
        return is_pr_from_travis()
    elif is_on_appveyor():
        return is_pr_from_appveyor()
    elif is_on_jenkins():
        return is_pr_from_jenkins()
    else:
        raise ValueError("Not on appveyor, travis or jenkins, so can't "
                         "resolve whether we are on a PR or not")


def branch_from_ci():
    if is_on_travis():
        return branch_from_travis()
    elif is_on_appveyor():
        return branch_from_appveyor()
    elif is_on_jenkins():
        return branch_from_jenkins()
    else:
        raise ValueError("We aren't on jenkins, "
                         "Appveyor or Travis so can't "
                         "decide on branch")


def resolve_can_upload_from_ci():
    # can upload as long as this isn't a PR
    can_upload = not is_pr_on_ci()
    print("Can we can upload (i.e. is this not a PR)? : {}".format(can_upload))
    return can_upload


def binstar_channel_from_ci(path):
    v = get_version(path)
    if is_release_tag(v):
        # tagged releases always go to main
        print("current head is a tagged release ({}), "
              "uploading to 'main' channel".format(v))
        return 'main'
    else:
        print('current head is not a release - interrogating CI to decide on '
              'channel to upload to (based on branch)')
        return branch_from_ci()


# -------------------- [EXPERIMENTAL] PYPI INTEGRATION ---------------------- #

# pypirc_path = p.join(p.expanduser('~'), '.pypirc')
# pypi_upload_allowed = (host_platform() == 'Linux' and
#                        host_arch() == 'x64' and
#                        sys.version_info.major == 2)
#
# pypi_template = """[distutils]
# index-servers = pypi
#
# [pypi]
# username:{}
# password:{}"""
#
#
# def pypi_setup_dotfile(username, password):
#     with open(pypirc_path, 'wb') as f:
#         f.write(pypi_template.format(username, password))
#
#
# def upload_to_pypi_if_appropriate(mc, username, password):
#     if username is None or password is None:
#         print('Missing PyPI username or password, skipping upload')
#         return
#     v = get_version()
#     if not is_release_tag(v):
#         print('Not on a tagged release - not uploading to PyPI')
#         return
#     if not pypi_upload_allowed:
#         print('Not on key node (Linux 64 Py2) - no PyPI upload')
#     print('Setting up .pypirc file..')
#     pypi_setup_dotfile(username, password)
#     print("Uploading to PyPI user '{}'".format(username))
#     execute_sequence([python(mc), 'setup.py', 'sdist', 'upload'])


# --------------------------- ARGPARSE COMMANDS ----------------------------- #

def miniconda_dir_cmd(_):
    set_globals_from_environ(verbose=False)
    print(miniconda_dir())


def setup_cmd(_):
    set_globals_from_environ()
    mc = miniconda_dir()
    setup_miniconda(mc, binstar_user=BINSTAR_USER)


def build_cmd(args):
    set_globals_from_environ()
    mc = miniconda_dir()
    conda_meta = args.meta_yaml_dir

    build_conda_package(mc, conda_meta, binstar_user=BINSTAR_USER)
    print('successfully built conda package, proceeding to upload')
    binstar_upload_if_appropriate(mc, conda_meta, BINSTAR_USER, BINSTAR_KEY)
    # upload_to_pypi_if_appropriate(mc, args.pypiuser, args.pypipassword)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('usage: condaci.py [-h] {setup,build,miniconda_dir} ...')
        sys.exit(1)

    from argparse import ArgumentParser
    pa = ArgumentParser(
        description=r"""
        Sets up miniconda, builds, and uploads to Binstar.
        """)
    subp = pa.add_subparsers()

    sp = subp.add_parser('setup', help='setup a miniconda environment')
    sp.set_defaults(func=setup_cmd)

    bp = subp.add_parser('build', help='run a conda build')
    bp.add_argument('meta_yaml_dir',
                    help="path to the dir containing the conda 'meta.yaml'"
                         "build script")

    mp = subp.add_parser('miniconda_dir',
                         help='path to the miniconda root directory')
    mp.set_defaults(func=miniconda_dir_cmd)

    bp.set_defaults(func=build_cmd)
    args = pa.parse_args()
    args.func(args)
