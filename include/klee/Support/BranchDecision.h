/*
Author: Jameson DiPalma
*/

// NEW includes struct for tracking control flow

#ifndef KLEE_CORE_BRANCHDECISION_H
#define KLEE_CORE_BRANCHDECISION_H

#include <string>

namespace klee {

struct BranchDecision {
  uint64_t branchId;
  unsigned instId;
  std::string filename;
  unsigned line;
  unsigned col;
  std::string condition;
  bool taken;
};

}

#endif // KLEE_CORE_BRANCHDECISION_H
