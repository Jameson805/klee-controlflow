/*
Author: Yuxiang Lin
*/

// NEW includes struct for tracking branches that can go both ways

#ifndef KLEE_CORE_BOTHBRANCH_H
#define KLEE_CORE_BOTHBRANCH_H

#include <vector>
#include <utility>
#include <memory>

namespace klee {

class ExecutionState;

struct BothBranch {
  unsigned branchId;
  using Assignments = std::vector<std::pair<std::string, std::vector<unsigned char>>>;
  std::pair<Assignments, Assignments> assignments;
};

}

#endif // KLEE_CORE_BOTHBRANCH_H
