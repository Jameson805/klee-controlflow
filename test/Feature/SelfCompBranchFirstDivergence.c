// RUN: %clang %s -g -emit-llvm %O0opt -c -o %t.bc
// RUN: rm -rf %t.klee-out
// RUN: %klee --output-dir=%t.klee-out --kdalloc --kdalloc-constants-size=1 --kdalloc-globals-size=1 --kdalloc-heap-size=1 --kdalloc-stack-size=1 %t.bc > /dev/null
// RUN: grep -R "localized branch side-channel" %t.klee-out

#include "klee/klee.h"

int main(void) {
	int secret;
	klee_make_symbolic_sc(&secret, sizeof(secret), "secret", 1);
	klee_assume(secret >= 0);
	klee_assume(secret < 2);

	if (secret) {
		return 1;
	}

	return 0;
}
