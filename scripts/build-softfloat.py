#!/usr/bin/env python
#=======================================================================
# build-softfloat.py
#=======================================================================
'''Builds the softfloat C library and exposes it to Python via CFFI.

The softfloat C library implements the IEEE 754 standard for
floating-point arithmetic, which is used in Pydgin to emulate hardware
floating-point units. While floating point operations can be emulated in
pure Python, the rules for calculating floating-point exception
conditions (e.g. overflow, underflow, inexact, etc.) is extremely
complex. Softfloat is widely used and validated, greatly simplifying the
implementation of floating point instructions in Pydgin.
'''

import cffi
import shutil
import subprocess
import sys

sys.path.append('..')

#-----------------------------------------------------------------------
# compiled the shared library with gcc
#-----------------------------------------------------------------------

compile_cmd = 'gcc -fPIC -shared ../softfloat/softfloat-c/*.c ' \
            + '-o libsoftfloat.so'

print compile_cmd

ret = subprocess.call( compile_cmd, shell=True )
if ret != 0:
  raise Exception('Compilation failed! Exiting.')

#-----------------------------------------------------------------------
# generate a python wrapper module with cffi
#-----------------------------------------------------------------------

ffi = cffi.FFI()
ffi.set_source('_abi', None)
ffi.cdef('''
    typedef uint32_t float32_t;
    typedef uint64_t float64_t;
    typedef struct { uint64_t v; uint16_t x; } floatx80_t;
    typedef struct { uint64_t v[ 2 ]; } float128_t;

    int_fast8_t softfloat_exceptionFlags;
    float32_t f32_add( float32_t a, float32_t b );
''')
ffi.compile()

shutil.move('_abi.py', '../softfloat/_abi.py')

#-----------------------------------------------------------------------
# verify everything went swimmingly
#-----------------------------------------------------------------------

from softfloat._abi import ffi
from pydgin.utils   import bits2float, float2bits

lib = ffi.dlopen('./libsoftfloat.so')

assert bits2float(0x3f800000) == 1.0

def test_add( is_inexact, out, a, b ):
  a_bits = float2bits(a)
  b_bits = float2bits(b)
  #print 'expected:', float2bits(out), out, lib.softfloat_exceptionFlags
  out_bits = lib.f32_add( a_bits, b_bits )
  #print 'actual:  ', out_bits, bits2float( out_bits ), is_inexact
  assert float2bits(out) == out_bits
  assert is_inexact == lib.softfloat_exceptionFlags
  #if out != bits2float( out_bits ):
  #  print "WARNING: bits match but float conversion doesn't!"
  #print
  lib.softfloat_exceptionFlags = 0


test_add( 0,                3.5,        2.5, 1.0 )
test_add( 1,              -1234,    -1235.1, 1.1 )
test_add( 1,         3.14159265, 3.14159265, 0.00000001 )
test_add( 0,                3.5,        2.5, 1.0 )
test_add( 1,              -1234,    -1235.1, 1.1 )

print 'softfloat library compiled and verified!'

