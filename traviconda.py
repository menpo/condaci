#!/usr/bin/env python
import subprocess
import os
import os.path as p
from functools import partial
import platform as stdplatform
import uuid
import sys


def is_on_appveyor():
    return 'APPVEYOR' in os.environ


def is_on_travis():
    return 'TRAVIS' in os.environ


def detect_arch():
    arch = stdplatform.architecture()[0]
    # need to be a little more sneaky to check the platform on Windows:
    # http://stackoverflow.com/questions/2208828/detect-64bit-os-windows-in-python
    if host_platform == 'Windows':
        if 'APPVEYOR' in os.environ:
            av_platform = os.environ['PLATFORM']
            if av_platform == 'x86':
                arch = '32bit'
            elif av_platform == 'x64':
                arch = '64bit'
            else:
                print('Was unable to interpret the platform "{}"'.format())
    return arch

host_platform = stdplatform.system()
host_arch = detect_arch()
pypi_upload_allowed = (host_platform == 'Linux' and
                       host_arch == '64bit' and
                       sys.version_info.major == 2)

url_win_script = 'https://raw.githubusercontent.com/jabooth/python-appveyor-conda-example/master/continuous-integration/appveyor/run_with_env.cmd'


def version_from_git_tags():
    raw = subprocess.check_output(['git', 'describe', '--tags']).strip()
    if sys.version_info.major == 3:
        # this always comes back as bytes. On Py3, convert to a string
        raw = raw.decode("utf-8")
    return raw[1:].replace('-', '_')  # always return a string (guaranteed)


try:
    os.environ['TC_PACKAGE_VERSION'] = version_from_git_tags()
except subprocess.CalledProcessError:
    print('Warning - unable to set TC_PACKAGE_VERSION')

pypirc_path = p.join(p.expanduser('~'), '.pypirc')

# define our commands
if host_platform == 'Windows':
    script_dir_name = 'Scripts'
    default_miniconda_dir = p.expanduser('C:\Miniconda')
    temp_installer_path = 'C:\{}.exe'.format(uuid.uuid4())
else:
    script_dir_name = 'bin'
    default_miniconda_dir = p.expanduser('~/miniconda')
    temp_installer_path = p.expanduser('~/{}.sh'.format(uuid.uuid4()))



miniconda_script_dir = lambda mc: p.join(mc, script_dir_name)

conda = lambda mc: p.join(miniconda_script_dir(mc), 'conda')
binstar = lambda mc: p.join(miniconda_script_dir(mc), 'binstar')
python = lambda mc: p.join(miniconda_script_dir(mc), 'python')

# Amazingly, adding these causes conda-build to fail parsing yaml. :-|
#print('running on {} {}'.format(platform, arch))
#print('miniconda_installer_path is {}'.format(miniconda_installer_path))
#print('miniconda will be installed to {}'.format(miniconda_dir))


def url_for_platform_version(platform, py_version, arch):
    version = '3.6.0'
    base_url = 'http://repo.continuum.io/miniconda/Miniconda'
    platform_str = {'Linux': 'Linux',
                    'Darwin': 'MacOSX',
                    'Windows': 'Windows'}
    arch_str = {'64bit': 'x86_64',
                '32bit': 'x86'}
    ext = {'Linux': '.sh',
           'Darwin': '.sh',
           'Windows': '.exe'}

    if py_version == '3':
        base_url = base_url + py_version
    return '-'.join([base_url, version,
                     platform_str[platform],
                     arch_str[arch]]) + ext[platform]

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
    print('opened process for cmd:{} with pid: {}'.format(cmd, proc.pid))
    sentinal = ''
    if sys.version_info.major == 3:
        sentinal = b''
    for line in iter(proc.stdout.readline, sentinal):
        if verbose:
            if sys.version_info.major == 3:
                # convert bytes to string
                line = line.decode("utf-8")
            sys.stdout.write(line)
            sys.stdout.flush()
    print('{}: no more new lines, waiting to terminate'.format(proc.pid))
    output = proc.communicate()[0]
    print('{} should have terminated fully. Final output is {}'.format(proc.pid, output))
    sys.stdout.write(output)
    sys.stdout.flush()
    if proc.returncode == 0:
        print('return code on {} is 0 process should have ended'.format(proc.pid))
        return output
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
    import urllib2
    f = urllib2.urlopen(url)
    with open(path_to_download, "wb") as fp:
        fp.write(f.read())
    fp.close()


# BINSTAR LOGIN

def login():
    from binstar_client.utils import get_binstar
    return get_binstar()


class LetMeIn:
    def __init__(self, key):
        self.token = key
        self.site = False


def login_with_key(key):
    from binstar_client.utils import get_binstar
    return get_binstar(args=LetMeIn(key))

# BINSTAR FILE PURGING


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


configuration_from_filename = lambda fn: fn.split('-')[-1].split('.')[0]
name_from_filename = lambda fn: fn.split('-')[0]
version_from_filename = lambda fn: fn.split('-')[1]
platform_from_filepath = lambda fp: p.split(p.split(fp)[0])[-1]
version_is_tag = lambda v: '_' not in v


def channels_for_user(b, user):
    return b.list_channels(user).keys()


def files_on_channel(b, user, channel):
    info = b.show_channel(channel, user)
    return [BinstarFile(i['full_name']) for i in info['files']]


def remove_file(b, bfile):
    b.remove_dist(bfile.user, bfile.name, bfile.version, bfile.basename)


def files_to_remove(b, user, channel, filepath):
    platform_ = platform_from_filepath(filepath)
    filename = p.split(filepath)[-1]
    name = name_from_filename(filename)
    version = version_from_filename(filename)
    configuration = configuration_from_filename(filename)
    # find all the files on this channel
    all_files = files_on_channel(b, user, channel)
    # other versions of this exact setup that are not tagged versions should
    # be removed
    return [f for f in all_files if
            f.name == name and
            f.configuration == configuration and
            f.platform == platform_ and
            f.version != version and
            not version_is_tag(f.version)]


def purge_old_files(b, user, channel, filepath):
    to_remove = files_to_remove(b, user, channel, filepath)
    print("Found {} releases to remove".format(len(to_remove)))
    for old_file in to_remove:
        print("Removing '{}'".format(old_file))
        remove_file(b, old_file)


# TRAVICONDA CONVENIENCE FUNCTIONS

def acquire_miniconda(url, path_to_download):
    print('Downloading miniconda from {} to {}'.format(url, path_to_download))
    download_file(url, path_to_download)


def install_miniconda(path_to_installer, path_to_install):
    print('Installing miniconda to {}'.format(path_to_install))
    if host_platform == 'Windows':
        execute([path_to_installer, '/S', '/D={}'.format(path_to_install)])
    else:
        execute(['chmod', '+x', path_to_installer])
        execute([path_to_installer, '-b', '-p', path_to_install])


def setup_miniconda(python_version, installation_path, channel=None):
    url = url_for_platform_version(host_platform, python_version, host_arch)
    print('Setting up miniconda from URL {}'.format(url))
    print("(Installing to '{}')".format(installation_path))
    acquire_miniconda(url, temp_installer_path)
    install_miniconda(temp_installer_path, installation_path)
    # delete the installer now we are done
    os.unlink(temp_installer_path)
    conda_cmd = conda(installation_path)
    cmds = [[conda_cmd, 'update', '-q', '--yes', 'conda'],
            [conda_cmd, 'install', '-q', '--yes', 'conda-build', 'jinja2',
             'binstar']]
    if channel is not None:
        print("(adding channel '{}' for dependencies)".format(channel))
        cmds.append([conda_cmd, 'config', '--add', 'channels', channel])
    else:
        print("No channels have been configured (all dependencies have to be "
              "sourced from anaconda)")
    execute_sequence(*cmds)


def conda_build_package_win_64bit(mc, path):
    temp_conda_build_script_path = 'C:\{}.cmd'.format(uuid.uuid4())
    print('downloading magical Windows SDK configuration script')
    download_file(url_win_script, temp_conda_build_script_path)
    # script expects PYTHON_VERSION set to either 2.7/3.4
    if sys.version_info.major == 2:
        os.environ['PYTHON_VERSION'] = '2.7'
    elif sys.version_info.major == 3:
        os.environ['PYTHON_VERSION'] = '3.4'
    # win_sdk_dir = 'C:\Program Files\Microsoft SDKs\Windows'
    # if sys.version_info.major == 2:
    #     win_sdk_version_str = "v7.0"
    # elif sys.version_info.major == 3:
    #     win_sdk_version_str = "v7.1"
    # else:
    #     raise ValueError('Unsupported major Python version')
    #
    # win_sdk_version_bin = '"{}"'.format(os.path.join(win_sdk_dir,
    #                                                  win_sdk_version_str,
    #                                                  'Setup',
    #                                                  'WindowsSdkVer.exe'))
    #
    # win_set_env_bin = '"{}"'.format(os.path.join(win_sdk_dir,
    #                                              win_sdk_version_str,
    #                                              'Bin', 'SetEnv.cmd'))
    # win_sdk_version_cmd = [win_sdk_version_bin, '-q',
    #                        '-version:{}'.format(win_sdk_version_str)]
    #
    # win_sdk_set_env_cmd = [win_set_env_bin, '/x64', '/release']

    # conda_build_cmd = ['call', '"{}"'.format(conda(mc)), 'build', '-q',
    #                    path, '||', 'EXIT', '1']
    #
    # os.environ['MSSdk'] = '1'
    # os.environ['DISTUTILS_USE_SDK'] = '1'

    # echo_finished_win_cmd = ['ECHO', 'finished setting env, about to build']
    # echo_finished_build_cmd = ['ECHO', 'finished conda build']
    # to_run = '\n'.join([' '.join(c) for c in [win_sdk_version_cmd,
    #                                           win_sdk_set_env_cmd]])
    # if sys.version_info.major == 3:
    #     to_run = to_run.encode("utf-8")  # convert from string to bytes
    # print(to_run)
    # temp_conda_build_script_path = 'C:\{}.cmd'.format(uuid.uuid4())
    # with open(temp_conda_build_script_path, 'wb') as f:
    #     f.write(to_run)
    print(subprocess.check_output(['cmd', '/E:ON', '/V:ON', '/C',
                                   temp_conda_build_script_path,
                                   conda(mc), 'build', '-q', path]))


def build_conda_package(mc, path):
    print('Building package at path {}'.format(path))
    if host_platform == 'Windows':
        if 'BINSTAR_KEY' in os.environ:
            print('found BINSTAR_KEY in environment on Windows - deleting to '
                  'stop vcvarsall from telling the world')
            del os.environ['BINSTAR_KEY']
        if host_arch == '64bit':
            print('running on 64 bit Windows - configuring Windows SDK before'
                  ' building')
            return conda_build_package_win_64bit(mc, path)
    # most of the time we are happy to just run conda build as normal
    execute([conda(mc), 'build', '-q', path])


def get_conda_build_path(path):
    from conda_build.metadata import MetaData
    from conda_build.build import bldpkg_path
    return bldpkg_path(MetaData(path))


def binstar_upload_unchecked(mc, key, user, channel, path):
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


def binstar_upload_if_appropriate(mc, path, user, key, channel=None):
    if key is None:
        print('No binstar key provided')
    if user is None:
        print('No binstar user provided')
    if user is None or key is None:
        print('-> Unable to upload to binstar')
        return
    print('Have a user ({}) and key - can upload if suitable'.format(user))
    # decide if we should attempt an upload
    if resolve_can_upload_from_ci():
        if channel is None:
            print('resolving channel from CI/git tags')
            channel = binstar_channel_from_ci()
        print("Fit to upload to channel '{}'".format(channel))
        binstar_upload_and_purge(mc, key, user, channel,
                                 get_conda_build_path(path))
    else:
        print("Cannot upload to binstar - must be a PR.")


def binstar_upload_and_purge(mc, key, user, channel, filepath):
    print('Uploading to {}/{}'.format(user, channel))
    binstar_upload_unchecked(mc, key, user, channel, filepath)
    b = login_with_key(key)
    if channel != 'main':
        print("Purging old releases from channel '{}'".format(channel))
        purge_old_files(b, user, channel, filepath)
    else:
        print("On main channel - no purging of releases will be done.")


def resolve_can_upload_from_ci():
    # can upload as long as this isn't a PR
    if is_on_travis():
        is_pr = is_pr_from_travis()
    elif is_on_appveyor():
        is_pr = is_pr_from_appveyor()
    else:
        raise ValueError('Not on app veyor or travis so cant '
                         'resolve whether we can upload')
    can_upload = not is_pr
    print("Can we can upload? : {}".format(can_upload))
    return can_upload


is_pr_from_travis = lambda: os.environ['TRAVIS_PULL_REQUEST'] != 'false'
is_pr_from_appveyor = lambda: 'APPVEYOR_PULL_REQUEST_NUMBER' in os.environ


def binstar_channel_from_ci():
    if git_head_has_tag():
        # tagged releases always go to main
        print("current head is a tagged release ({}), "
              "uploading to 'main' channel".format(version_from_git_tags()))
        return 'main'
    if is_on_travis():
        return branch_from_travis()
    elif is_on_appveyor():
        return branch_from_appveyor()
    else:
        raise ValueError("An untagged release, and we aren't on "
                         "Appveyor or Travis so can't "
                         "decide on binstar channel")


branch_from_appveyor = lambda: os.environ['APPVEYOR_REPO_BRANCH']
branch_from_travis = lambda: os.environ['TRAVIS_BRANCH']


pypi_template = """[distutils]
index-servers = pypi

[pypi]
username:{}
password:{}"""


def pypi_setup_dotfile(username, password):
    with open(pypirc_path, 'wb') as f:
        f.write(pypi_template.format(username, password))


def upload_to_pypi_if_appropriate(mc, username, password):
    if username is None or password is None:
        print('Missing PyPI username or password, skipping upload')
        return
    if not git_head_has_tag():
        print('Not on a tagged release - not uploading to PyPI')
        return
    if not pypi_upload_allowed:
        print('Not on key node (Linux 64 Py2) - no PyPI upload')
    print('Setting up .pypirc file..')
    pypi_setup_dotfile(username, password)
    print("Uploading to PyPI user '{}'".format(username))
    execute_sequence([python(mc), 'setup.py', 'sdist', 'upload'])


def git_head_has_tag():
    try:
        execute(['git', 'describe', '--exact-match', '--tags', 'HEAD'])
        return True
    except subprocess.CalledProcessError:
        return False


def setup_cmd(args):
    mc = resolve_mc(args.path)
    setup_miniconda(args.python, mc, channel=args.channel)


def build_cmd(args):
    mc = resolve_mc(args.miniconda)
    build_conda_package(mc, args.buildpath)


def binstar_cmd(args):
    mc = resolve_mc(args.miniconda)
    print('binstar being called with args: {}'.format(args))
    binstar_upload_if_appropriate(mc, args.buildpath, args.binstaruser,
                                  args.binstarkey, channel=args.binstarchannel)


def pypi_cmd(args):
    mc = resolve_mc(args.miniconda)
    upload_to_pypi_if_appropriate(mc, args.pypiuser, args.pypipassword)


def version_cmd(_):
    print(version_from_git_tags())


def auto_cmd(args):
    mc = resolve_mc(args.miniconda)
    build_conda_package(mc, args.buildpath)
    print('successfully built conda package, proceeding to upload')
    binstar_upload_if_appropriate(mc, args.buildpath, args.binstaruser,
                                  args.binstarkey,
                                  channel=args.binstarchannel)
    #upload_to_pypi_if_appropriate(mc, args.pypiuser, args.pypipassword)


def resolve_mc(mc):
    if mc is not None:
        return mc
    else:
        return default_miniconda_dir


def add_miniconda_parser(parser):
    parser.add_argument(
        "-m", "--miniconda",
        help="directory that miniconda is installed in (if not provided "
             "taken as '{}')".format(default_miniconda_dir))


def add_pypi_parser(pa):
    pa.add_argument('--pypiuser',  nargs='?', default=None,
                    help='PyPI user to upload to')
    pa.add_argument('--pypipassword', nargs='?', default=None,
                    help='password of PyPI user')


def add_buildpath_parser(pa):
    pa.add_argument('buildpath',
                    help="path to the conda build scripts")


def add_binstar_parser(pa):
    pa.add_argument('--binstaruser', nargs='?', default=None,
                    help='Binstar user (or organisation) to upload to')
    pa.add_argument('--binstarchannel', nargs='?', default=None,
                    help='Binstar channel to uplaod to. If not provided will'
                         ' be calculated based on the environment')
    pa.add_argument('--binstarkey', nargs='?', default=None,
                    help='Binstar API key to use for uploading')


if __name__ == "__main__":
    from argparse import ArgumentParser
    pa = ArgumentParser(
        description=r"""
        Sets up miniconda, builds, and uploads to Binstar and PyPI.
        """)
    subp = pa.add_subparsers()

    sp = subp.add_parser('setup', help='setup a miniconda environment')
    sp.add_argument("python", choices=['2', '3'])
    sp.add_argument('-p', '--path', help='the path to install miniconda to. '
                                         'If not provided defaults to {'
                                         '}'.format(default_miniconda_dir))
    sp.add_argument("-c", "--channel",
                    help="binstar channel to activate")
    sp.set_defaults(func=setup_cmd)

    bp = subp.add_parser('build', help='run a conda build')
    add_buildpath_parser(bp)
    add_miniconda_parser(bp)
    bp.set_defaults(func=build_cmd)

    bin = subp.add_parser('binstar', help='upload a conda build to binstar')
    add_buildpath_parser(bin)
    add_binstar_parser(bin)
    add_miniconda_parser(bin)
    bin.set_defaults(func=binstar_cmd)

    pypi = subp.add_parser('pypi', help='upload a source distribution to PyPI')
    add_pypi_parser(pypi)
    add_miniconda_parser(pypi)
    pypi.set_defaults(func=pypi_cmd)

    auto = subp.add_parser('auto', help='build and upload to binstar and pypi')
    add_buildpath_parser(auto)
    add_binstar_parser(auto)
    add_miniconda_parser(auto)
    add_pypi_parser(auto)
    auto.set_defaults(func=auto_cmd)

    vp = subp.add_parser('version', help='print the version as reported by '
                                         'git')
    vp.set_defaults(func=version_cmd)

    args = pa.parse_args()
    args.func(args)
