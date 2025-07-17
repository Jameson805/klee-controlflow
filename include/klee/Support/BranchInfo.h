/*
Author: Jameson DiPalma, Yuxiang Lin
*/

// NEW includes struct for tracking control flow

#ifndef KLEE_CORE_BRANCHDECISION_H
#define KLEE_CORE_BRANCHDECISION_H

#include <string>

namespace klee {

struct BranchInfo {
  unsigned instId;
  std::string filename;
  unsigned line;
  unsigned col;
  std::string condition;

  int count{0};
  int bothCount{0};

  BranchInfo(unsigned instId, const std::string &filename,
    unsigned line, unsigned col, const std::string &condition)
  : instId{instId}, filename{filename}, line{line}, col{col}, condition{condition}
  {
  }

  BranchInfo(const BranchInfo &b) = default;
};

struct BranchDecision {
  uint64_t instId;
  uint64_t branchId;
  bool taken;
};

}

#endif // KLEE_CORE_BRANCHDECISION_H
