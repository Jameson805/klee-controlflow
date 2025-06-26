/*
Author: Jameson DiPalma
*/

// NEW includes struct for tracking control flow

#ifndef KLEE_CORE_BRANCHDECISION_H
#define KLEE_CORE_BRANCHDECISION_H

#include <string>

namespace klee {

struct BranchDecision {
  std::string filename;
  unsigned line;
  std::string condition;
  bool taken;
};

}

#endif // KLEE_CORE_BRANCHDECISION_H
