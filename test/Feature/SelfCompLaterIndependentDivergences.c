// RUN: %clang %s -g -emit-llvm %O0opt -c -o %t.bc
// RUN: rm -rf %t.klee-out
// RUN: %klee --output-dir=%t.klee-out --kdalloc --kdalloc-constants-size=1 --kdalloc-globals-size=1 --kdalloc-heap-size=1 --kdalloc-stack-size=1 %t.bc > %t.stdout 2>&1
// RUN: grep -E "\\[NON-CT BRANCH\\].*SelfCompLaterIndependentDivergences.c : 21 :" %t.stdout
// RUN: grep -E "\\[NON-CT MEMORY\\].*SelfCompLaterIndependentDivergences.c : 22 :" %t.stdout
// RUN: grep -E "\\[NON-CT MEMORY\\].*SelfCompLaterIndependentDivergences.c : 23 :" %t.stdout
// RUN: grep -F "[BRANCH]" %t.klee-out/messages.txt
// RUN: grep -F "[MEMORY]" %t.klee-out/messages.txt

#include "klee/klee.h"

int table_a[4];
int out[4];

int main(void) {
  int secret;

  klee_make_symbolic_sc(&secret, sizeof(secret), "secret", 1);
  secret &= 7;

  if (secret & 4) {
    out[secret & 1] = 1;
    table_a[(secret >> 1) & 3] = 2;
  } else {
    out[2] = 1;
  }

  return 0;
}