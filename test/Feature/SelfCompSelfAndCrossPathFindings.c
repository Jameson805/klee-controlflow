// RUN: %clang %s -g -emit-llvm %O0opt -c -o %t.bc
// RUN: rm -rf %t.klee-out
// RUN: %klee --output-dir=%t.klee-out --kdalloc --kdalloc-constants-size=1 --kdalloc-globals-size=1 --kdalloc-heap-size=1 --kdalloc-stack-size=1 %t.bc > %t.stdout 2>&1
// RUN: grep -F "[NON-CT MEMORY]" %t.stdout
// RUN: grep -F "[NON-CT BRANCH]" %t.stdout
// RUN: grep -F "[MEMORY]" %t.klee-out/messages.txt
// RUN: grep -F "[BRANCH]" %t.klee-out/messages.txt
// RUN: grep -R "localized memory side-channel" %t.klee-out
// RUN: grep -R "localized branch side-channel" %t.klee-out

#include "klee/klee.h"

int a[4];

int main(void) {
  int sec;
  klee_make_symbolic_sc(&sec, sizeof(sec), "sec", 1);
  sec &= 3;

  if (sec & 1) {
    a[sec & 1] = 1;
    a[sec & 2] = 1;
    a[sec] = 1;
  }

  return 0;
}
