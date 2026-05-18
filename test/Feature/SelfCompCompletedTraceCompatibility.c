// RUN: %clang %s -g -emit-llvm %O0opt -c -o %t.bc
// RUN: rm -rf %t.klee-out
// RUN: %klee --output-dir=%t.klee-out --kdalloc --kdalloc-constants-size=1 --kdalloc-globals-size=1 --kdalloc-heap-size=1 --kdalloc-stack-size=1 %t.bc > %t.stdout 2>&1
// RUN: grep -E "\\[NON-CT BRANCH\\].*SelfCompCompletedTraceCompatibility.c : 28 :" %t.stdout
// RUN: grep -E "\\[NON-CT MEMORY\\].*SelfCompCompletedTraceCompatibility.c : 29 :" %t.stdout
// RUN: grep -E "\\[NON-CT MEMORY\\].*SelfCompCompletedTraceCompatibility.c : 30 :" %t.stdout
// RUN: grep -E "\\[NON-CT MEMORY\\].*SelfCompCompletedTraceCompatibility.c : 35 :" %t.stdout
// RUN: not grep -E "\\[NON-CT BRANCH\\].*SelfCompCompletedTraceCompatibility.c : 37 :" %t.stdout

#include "klee/klee.h"

int table_a[4];
int table_b[4];
int out[8];

int main(void) {
  int pub;
  int secret;

  klee_make_symbolic(&pub, sizeof(pub), "pub");
  klee_make_symbolic_sc(&secret, sizeof(secret), "secret", 1);

  pub &= 1;
  secret &= 7;

  int base = pub ? 4 : 0;

  if (secret & 4) {
    out[base + (secret & 1)] = 1;
    table_a[(secret >> 1) & 3] = 2;
  } else {
    out[base + 2] = 1;
  }

  out[base + ((secret ^ pub) & 3)] += 3;

  if ((secret & 3) == 3) {
    table_b[(secret ^ 1) & 3] = 4;
  }

  return 0;
}