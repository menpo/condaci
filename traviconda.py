#!/usr/bin/env python
import subprocess
import os
import os.path as p
from functools import partial
import platform as stdplatform

platform = stdplatform.system()


def detect_arch():
    arch = stdplatform.architecture()[0]

    # need to be a little more sneaky to check the platform on Windows:
    # http://stackoverflow.com/questions/2208828/detect-64bit-os-windows-in-python
    if platform == 'Windows':
        if 'APPVEYOR' in os.environ:
            print("Running on AppVeyor, can check arch directly")
            av_platform = os.environ['PLATFORM']
            if av_platform == 'x86':
                arch = '32bit'
            elif av_platform == 'x64':
                arch = '64bit'
            else:
                print('Was unable to interpret the platform "{}"'.format())
    return arch

arch = detect_arch()

print('running on {} {}'.format(platform, arch))


# define our commands
if platform == 'Windows':
    script_dir_name = 'Scripts'
    miniconda_installer_path = 'C:\miniconda.exe'
    miniconda_dir = p.expanduser('C:\Miniconda')
else:
    script_dir_name = 'bin'
    miniconda_installer_path = p.expanduser('~/miniconda.sh')
    miniconda_dir = p.expanduser('~/miniconda')

#print('miniconda_installer_path is {}'.format(miniconda_installer_path))
#print('miniconda will be installed to {}'.format(miniconda_dir))

miniconda_script_dir = p.join(miniconda_dir, script_dir_name)
conda = p.join(miniconda_script_dir, 'conda')
binstar = p.join(miniconda_script_dir, 'binstar')
python = 'python'


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
    import urllib2
    f = urllib2.urlopen(url)
    with open(path_to_download, "wb") as fp:
        fp.write(f.read())


def acquire_miniconda(url, path_to_download):
    print('Downloading miniconda from {} to {}'.format(url, path_to_download))
    download_file(url, path_to_download)


def install_miniconda(path_to_installer, path_to_install):
    print('Installing miniconda to {}'.format(path_to_install))
    if platform == 'Windows':
        execute([path_to_installer, '/S', '/D={}'.format(path_to_install)])
    else:
        execute(['chmod', '+x', path_to_installer])
        execute([path_to_installer, '-b', '-p', path_to_install])


def setup_miniconda(python_version, channel=None):
    url = url_for_platform_version(platform, python_version, arch)
    print('Setting up miniconda from URL {}'.format(url))
    acquire_miniconda(url, miniconda_installer_path)
    install_miniconda(miniconda_installer_path, miniconda_dir)
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


def build_and_upload(path, user=None, key=None):
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
    # decide if we should attempt an upload
    if resolve_can_upload_from_travis():
        channel = resolve_channel_from_travis_state()
        print('Uploading to {}/{}'.format(user, channel))
        binstar_upload(key, user, channel, get_conda_build_path(path))


def resolve_can_upload_from_travis():
    is_a_pr = os.environ['TRAVIS_PULL_REQUEST'] == 'true'
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


if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser(
        description=r"""
        Sets up miniconda, builds, and uploads to binstar on Travis CI.
        """)
    parser.add_argument("mode", choices=['setup', 'build', 'version'])
    parser.add_argument("--python", choices=['2', '3'])
    parser.add_argument("-c", "--channel", help="binstar channel to activate "
                                                "(setup only, optional)")
    parser.add_argument("--path", help="path to the conda build "
                                             "scripts (build only, required)")
    parser.add_argument("-u", "--user", help="binstar user to upload to "
                                             "(build only, required to "
                                             "upload)")
    parser.add_argument("-k", "--key", help="The binstar key for uploading ("
                                            "build only, required to upload)")
    ns = parser.parse_args()

    if ns.mode == 'setup':
        setup_miniconda(ns.python, channel=ns.channel)
    elif ns.mode == 'build':
        build_and_upload(ns.path, user=ns.user, key=ns.key)
    else:
        print(version_from_git_tags())
