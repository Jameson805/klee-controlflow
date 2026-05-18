// RUN: %clang %s -g -emit-llvm %O0opt -c -o %t.bc
// RUN: rm -rf %t.klee-out
// RUN: %klee --output-dir=%t.klee-out --kdalloc --kdalloc-constants-size=1 --kdalloc-globals-size=1 --kdalloc-heap-size=1 --kdalloc-stack-size=1 %t.bc > /dev/null
// RUN: grep -R "localized memory side-channel" %t.klee-out

#include "klee/klee.h"

int main(void) {
  int left = 11;
  int right = 29;
  int *table[2] = {&left, &right};
  int secret_index;

  klee_make_symbolic_sc(&secret_index, sizeof(secret_index), "secret_index", 1);
  klee_assume(secret_index >= 0);
  klee_assume(secret_index < 2);

  int *selected = table[secret_index];
  return *selected;
}
