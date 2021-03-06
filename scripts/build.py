#!/usr/bin/env python
#=========================================================================
# build.py
#=========================================================================
# Builds pydgin.

import multiprocessing
import os
import shutil
import sys
import subprocess
import distutils.spawn

all_targets = [ "pydgin-parc-jit", "pydgin-parc-nojit-debug",
                "pydgin-arm-jit", "pydgin-arm-nojit-debug",
                "pydgin-riscv-jit", "pydgin-riscv-nojit-debug" ]

usage = """Usage:
  ./build.py [flags] [targets]
  Flags: -h,--help   this help message
         -jN         parallelize for N cores (omit N for # of processors)
         --batch     pass --batch flag to rpython (don't fall to pdb on error)
  Targets: 'all' or one or more of the following:
           {}
""".format( ", ".join( all_targets ) )

def build_target( name, pypy_dir, build_dir, extra_rpython_flags ):

  # use the name to determine the arch, jit, softfloat requirement, and debug

  arch = None
  require_softfloat = False
  if "parc" in name:
    arch = "parc"
  if "arm" in name:
    assert arch is None, "conflicting arch definitions {} and {}" \
                         .format( arch, "arm" )
    arch = "arm"
  if "riscv" in name:
    assert arch is None, "conflicting arch definitions {} and {}" \
                         .format( arch, "riscv" )
    arch = "riscv"
    # risc-v is the only architecture that requires softfloat for now
    require_softfloat = True
  assert arch is not None, "could not determine arch from name"

  # check if we have already built softfloat and if not, build it
  if require_softfloat:
    # check os to find which extension to check for (we only support mac
    # or linux)
    assert sys.platform == "linux" or sys.platform == "linux2" \
          or sys.platform == "darwin"

    softfloat_file = "libsoftfloat.dylib" if sys.platform == "darwin" \
          else "libsoftfloat.so"

    print "softfloat is required, checking if {} exists..." \
          .format( softfloat_file ),
    found_softfloat = os.path.isfile( softfloat_file )

    if not found_softfloat:
      print "no"
      print "calling build-softfloat.py to build it"
      cmd = "../scripts/build-softfloat.py"
      print cmd
      ret = subprocess.call( cmd, shell=True )

      # check for success and if the file exists

      if ret != 0:
        print "softfloat library could not be built, aborting!"
        sys.exit( ret )

      if not os.path.isfile( softfloat_file ):
        print "{} could not be found, aborting!".format( softfloat_file )
        sys.exit( ret )

    else:
      print "yes"

  if "jit" in name and "nojit" not in name:
    jit = True
  elif "nojit" in name:
    jit = False
  else:
    # default behavior if neither jit or nojit in name
    jit = True

  if "debug" in name and "nodebug" not in name:
    debug = True
  elif "nodebug" in name:
    debug = False
  else:
    # default behavior if neither debug or nodebug in name
    debug = False

  print "Building {}\n  arch: {}\n  jit: {}\n  debug: {}\n" \
        .format( name, arch, jit, debug )

  # check for the pypy executable, if it doesn't exist warn

  python_bin = distutils.spawn.find_executable('pypy')
  if not python_bin:
    print ('WARNING: Cannot find a pypy executable!\n'
           '  Proceeding to translate with CPython.\n'
           '  Note that this will be *much* slower than using pypy.\n'
           '  Please install pypy for faster translation times!\n')
    python_bin = 'python'

  # create the translation command and execute it

  os.chdir('../{}'.format( arch ) )
  cmd = ( '{python_bin} {pypy_dir}/rpython/bin/rpython {rpython_opts} '
          '{arch}-sim.py {pydgin_opts}' ) \
          .format( arch=arch, pypy_dir=pypy_dir,
                   rpython_opts=( extra_rpython_flags +
                                  ("--opt=jit" if jit   else "") ),
                   pydgin_opts =( "--debug"   if debug else "" ),
                   python_bin=python_bin )

  print cmd
  ret = subprocess.call( cmd, shell=True )

  # check for success and cleanup

  if ret != 0:
    print "{} failed building, aborting!".format( name )
    sys.exit( ret )

  # for some reason, -rpath to the linker doesn't seem to work on macs?
  # we patch the binary generated to add the exact dir of libsoftfloat.so

  if require_softfloat and sys.platform == "darwin":
    cmd = "install_name_tool -change {short_so} {full_so} {pydgin}" \
          .format( short_so="libsoftfloat.so",
                   full_so="{}/../../../libsoftfloat.so".format( build_dir ),
                   pydgin=name )
    print cmd
    subprocess.call( cmd, shell=True )

  shutil.copy( name, '{}'.format( build_dir ) )
  symlink_name = '{}/../{}'.format( build_dir, name )
  if os.path.lexists( symlink_name ):
    os.remove( symlink_name )
  os.symlink( '{}/{}'.format( build_dir, name ), symlink_name )

def setup_environment():
  # assume if arg starts with a dash, it's a flag
  args = sys.argv[1:]

  flags   = filter( lambda x: x.startswith('-'), args )
  targets = filter( lambda x: not x.startswith('-'), args )

  # don't parallelize by default
  num_processes = 1

  extra_rpython_flags = ""

  for flag in flags:
    if flag == '-h' or flag == '--help':
      print usage
      sys.exit( 1 )
    elif flag.startswith( '-j' ):
      if flag == '-j':
        # get the cpu count
        num_processes = multiprocessing.cpu_count()
      else:
        num_processes = int( flag[2:] )
    elif flag == "--batch":
      extra_rpython_flags += "--batch "
    else:
      print "Unknown flag:", flag
      print usage
      sys.exit( 1 )

  # ensure we know where the pypy source code is
  try:
    pypy_dir = os.environ['PYDGIN_PYPY_SRC_DIR']
  except KeyError as e:
    raise ImportError( 'Please define the PYDGIN_PYPY_SRC_DIR '
                       'environment variable!')

  # all includes all_targets
  if "all" in targets:
    targets += all_targets
    targets.remove( "all" )

  # unique-ify
  targets = list( set( targets ) )

  # if there are no targets, we add all
  if len( targets ) == 0:
    targets = all_targets

  # get the version number
  pydgin_ver = subprocess.check_output(
                               "../scripts/vcs-version.sh", shell=True ).rstrip()

  print "Building Pydgin..."
  print "Version: {}".format( pydgin_ver )
  print "PyPy source: {}".format( pypy_dir )
  print "Targets: {}".format( targets )
  print "Number of processes: {}".format( num_processes )

  # create build dir
  cwd = os.getcwd()
  build_dir = "{}/builds/pydgin-{}/bin".format( cwd, pydgin_ver )
  subprocess.call( "mkdir -p {}".format( build_dir ), shell=True )

  return targets, pypy_dir, build_dir, num_processes, extra_rpython_flags


def main():
  # get targets and environment
  targets, pypy_dir, build_dir, num_processes, extra_rpython_flags \
                                                      = setup_environment()

  # don't parallelize for 1 process
  if num_processes <= 1:
    for target in targets:
      build_target( target, pypy_dir, build_dir, extra_rpython_flags )

  else:
    # build targets in parallel
    pool = multiprocessing.Pool( processes=num_processes )
    try:
      for target in targets:
        pool.apply_async( build_target,
                          [target, pypy_dir, build_dir, extra_rpython_flags] )

      pool.close()
      pool.join()
    except KeyboardInterrupt:
      print "Terminating workers!"
      pool.terminate()
      pool.join()

    print 'Parallel builds complete.'


if __name__ == "__main__":
  main()

