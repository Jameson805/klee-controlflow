// RUN: %clang %s -g -emit-llvm %O0opt -c -o %t.bc
// RUN: rm -rf %t.klee-out
// RUN: %klee --output-dir=%t.klee-out --kdalloc --kdalloc-constants-size=1 --kdalloc-globals-size=1 --kdalloc-heap-size=1 --kdalloc-stack-size=1 %t.bc > %t.stdout 2>&1
// RUN: grep -F "[NON-CT MEMORY]" %t.stdout
// RUN: ls %t.klee-out/memory_counterexample_*.ktest
// RUN: %ktest-tool --extract secret %t.klee-out/memory_counterexample_*.ktest
// RUN: %ktest-tool --extract secret__prime %t.klee-out/memory_counterexample_*.ktest
// RUN: not cmp -s %t.klee-out/memory_counterexample_*.ktest.secret %t.klee-out/memory_counterexample_*.ktest.secret__prime

#include "klee/klee.h"

int table[2];

int main(void) {
  unsigned secret;

  klee_make_symbolic_sc(&secret, sizeof(secret), "secret", 1);
  secret &= 1;
  table[secret] = 1;

  return 0;
}