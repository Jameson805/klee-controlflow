/*===-- explicit_bzero.c --------------------------------------------------===//
//
//                     The KLEE Symbolic Virtual Machine
//
// This file is distributed under the University of Illinois Open Source
// License. See LICENSE.TXT for details.
//
//===----------------------------------------------------------------------===*/

#include <stddef.h>

void explicit_bzero(void *dst, size_t count) {
  char *a = dst;
  while (count-- > 0)
    *a++ = 0;
}
