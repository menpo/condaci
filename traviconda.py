#!/usr/bin/env python
import subprocess
import os
import os.path as p
from functools import partial
import platform as stdplatform


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


# define our commands
if host_platform == 'Windows':
    script_dir_name = 'Scripts'
    default_installer_path = 'C:\miniconda.exe'
    default_miniconda_dir = p.expanduser('C:\Miniconda')
else:
    script_dir_name = 'bin'
    default_installer_path = p.expanduser('~/miniconda.sh')
    default_miniconda_dir = p.expanduser('~/miniconda')

miniconda_script_dir = p.join(default_miniconda_dir, script_dir_name)
conda = p.join(miniconda_script_dir, 'conda')
binstar = p.join(miniconda_script_dir, 'binstar')
python = 'python'

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
co = partial(subprocess.check_output, stderr=subprocess.STDOUT)
check = partial(subprocess.check_call, stderr=subprocess.STDOUT)


def execute(cmd, verbose=False):
    r""" Runs a command, printing the command and it's output to screen.
    """
    if verbose:
        print('> {}'.format(' '.join(cmd)))
    result = co(cmd)
    if verbose:
        print(result)
    return result


def execute_sequence(*cmds, **kwargs):
    r""" Execute a sequence of commands. If any fails, display an error.
    """
    verbose = kwargs.get('verbose', True)
    try:
        for cmd in cmds:
            execute(cmd, verbose)
    except subprocess.CalledProcessError as e:
        print(' -> {}'.format(e.output))
        raise e


def download_file(url, path_to_download):
    if p.exists(path_to_download):
        raise ValueError('Cannot download file to {} - '
                         'file exists'.format(path_to_download))
    import urllib2
    f = urllib2.urlopen(url)
    with open(path_to_download, "wb") as fp:
        fp.write(f.read())


# BINSTAR LOGIN

def login():
    from binstar_client.utils import get_binstar
    return get_binstar()


class LetMeIn:
    def __init__(self, key):
        self.token = key


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


# TRAVICONDA CONVIENIENCE FUNCTIONS


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
    acquire_miniconda(url, default_installer_path)
    install_miniconda(default_installer_path, installation_path)
    cmds = [[conda, 'update', '-q', '--yes', 'conda'],
            [conda, 'install', '-q', '--yes', 'conda-build', 'jinja2',
             'binstar']]
    if channel is not None:
        print("(adding channel '{}' for dependencies)".format(channel))
        cmds.append([conda, 'config', '--add', 'channels', channel])
    else:
        print("No channels have been configured (all dependencies have to be "
              "sourced from anaconda)")
    execute_sequence(*cmds)


def build(path):
    execute_sequence([conda, 'build', '-q', path])


def get_conda_build_path(path):
    from conda_build.metadata import MetaData
    from conda_build.build import bldpkg_path
    return bldpkg_path(MetaData(path))


def binstar_upload(key, user, channel, path):
    try:
        # TODO - could this safely be co? then we would get the binstar error..
        check([binstar, '-t', key, 'upload',
               '--force', '-u', user, '-c', channel, path])
    except subprocess.CalledProcessError as e:
        # mask the binstar key...
        cmd = e.cmd
        cmd[2] = 'BINSTAR_KEY'
        # ...then raise the error
        raise subprocess.CalledProcessError(e.returncode, cmd)


def build_upload_and_purge(path, user=None, key=None):
    print('Building package at path {}'.format(ns.path))
    # actually issue conda build
    build(path)
    if key is None:
        print('No binstar key provided')
    if user is None:
        print('No binstar user provided')
    if user is None or key is None:
        print('-> Unable to upload to binstar')
        return
    print('Have a user ({}) and key - can upload if suitable'.format(user))
    # decide if we should attempt an upload
    if resolve_can_upload_from_travis():
        channel = resolve_channel_from_travis_state()
        print("Fit to upload to channel '{}'".format(channel))
        upload_and_purge(key, user, channel, get_conda_build_path(path))
    else:
        print("Cannot upload to binstar - must be a PR.")


def upload_and_purge(key, user, channel, filepath):
    print('Uploading to {}/{}'.format(user, channel))
    binstar_upload(key, user, channel, filepath)
    b = login_with_key(key)
    if channel != 'main':
        print("Purging old releases from channel '{}'".format(channel))
        purge_old_files(b, user, channel, filepath)
    else:
        print("On main channel - no purging of releases will be done.")


def resolve_can_upload_from_travis():
    is_a_pr = os.environ['TRAVIS_PULL_REQUEST'] != 'false'
    can_upload = not is_a_pr
    print("Can we can upload? : {}".format(can_upload))
    return can_upload


def resolve_channel_from_travis_state():
    branch = os.environ['TRAVIS_BRANCH']
    tag = os.environ['TRAVIS_TAG']
    print('Travis branch is "{}"'.format(branch))
    print('Travis tag found is: "{}"'.format(tag))
    if tag != '' and branch == tag:
        # final release, channel is 'main'
        print("on a tagged release -> upload to 'main'")
        return 'main'
    else:
        print("not on a tag on master - "
              "just upload to the branch name {}".format(branch))
        return branch


def version_from_git_tags():
    return subprocess.check_output(
        ['git', 'describe', '--tags']).strip()[1:].replace('-', '_')


def setup_cmd(ns):
    print ns
    if ns.path is None:
        path = default_miniconda_dir
    else:
        path = ns.path
    setup_miniconda(ns.python, path, channel=ns.channel)


def build_cmd(ns):
    build_upload_and_purge(ns.path, user=ns.user, key=ns.key)


def upload_cmd(args):
    print('upload being called with args: {}'.format(args))


def version_cmd(_):
    print(version_from_git_tags())


if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser(
        description=r"""
        Sets up miniconda, builds, and uploads to binstar on Travis CI.
        """)
    subp = parser.add_subparsers()

    sp = subp.add_parser('setup', help='setup a miniconda environment')
    sp.add_argument("python", choices=['2', '3'])
    sp.add_argument('-p', '--path', help='The path to install miniconda to. '
                                         'If not provided defaults to {'
                                         '}'.format(default_miniconda_dir))
    sp.add_argument("-c", "--channel",
                    help="binstar channel to activate")
    sp.set_defaults(func=setup_cmd)


    bp = subp.add_parser('build', help='run a conda build')
    bp.add_argument("path", help="path to the conda build scripts")
    bp.set_defaults(func=build_cmd)


    up = subp.add_parser('upload', help='upload a conda build to binstar')
    up.add_argument('path', help='path to the conda build scripts')
    up.add_argument('user', help='Binstar user(or organisation) to upload to')
    up.add_argument('key', help='Binstar API key to use for uploading')
    up.set_defaults(func=upload_cmd)

    vp = subp.add_parser('version', help='print the version as reported by '
                                         'git')
    vp.set_defaults(func=version_cmd)

    args = parser.parse_args()
    args.func(args)
