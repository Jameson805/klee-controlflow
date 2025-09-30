//===-- Constraints.h -------------------------------------------*- C++ -*-===//
//
//                     The KLEE Symbolic Virtual Machine
//
// This file is distributed under the University of Illinois Open Source
// License. See LICENSE.TXT for details.
//
//===----------------------------------------------------------------------===//

#ifndef KLEE_CONSTRAINTS_H
#define KLEE_CONSTRAINTS_H

#include "klee/Expr/Expr.h"

#include <optional>

namespace klee {

/// Resembles a set of constraints that can be passed around
///
class ConstraintSet {
  friend class ConstraintManager;

public:
  using constraints_ty = std::vector<ref<Expr>>;
  using iterator = constraints_ty::iterator;
  using const_iterator = constraints_ty::const_iterator;

  using constraint_iterator = const_iterator;

  bool empty() const;
  constraint_iterator begin() const;
  constraint_iterator end() const;
  size_t size() const noexcept;

  explicit ConstraintSet(constraints_ty cs, std::vector<std::optional<unsigned>> insts) : constraints(std::move(cs)), constraintInsts(std::move(insts)) {}
  explicit ConstraintSet(constraints_ty cs) : constraints(std::move(cs)), constraintInsts(std::vector<std::optional<unsigned>>(cs.size(), std::nullopt)) {}
  ConstraintSet() = default;

  void push_back(const ref<Expr> &e, std::optional<unsigned> inst = std::nullopt);

  bool operator==(const ConstraintSet &b) const {
    return constraints == b.constraints;
  }

  const std::vector<std::optional<unsigned>>& getInsts() const {
    return constraintInsts;
  }

private:
  constraints_ty constraints;
  // Instructions that added the constraints
  std::vector<std::optional<unsigned>> constraintInsts;
};

class ExprVisitor;

/// Manages constraints, e.g. optimisation
class ConstraintManager {
public:
  /// Create constraint manager that modifies constraints
  /// \param constraints
  explicit ConstraintManager(ConstraintSet &constraints);

  /// Simplify expression expr based on constraints
  /// \param constraints set of constraints used for simplification
  /// \param expr to simplify
  /// \return simplified expression
  static ref<Expr> simplifyExpr(const ConstraintSet &constraints,
                                const ref<Expr> &expr);

  /// Add constraint to the referenced constraint set
  /// \param constraint
  void addConstraint(const ref<Expr> &constraint, std::optional<unsigned> inst = std::nullopt);

private:
  /// Rewrite set of constraints using the visitor
  /// \param visitor constraint rewriter
  /// \return true iff any constraint has been changed
  bool rewriteConstraints(ExprVisitor &visitor);

  /// Add constraint to the set of constraints
  void addConstraintInternal(const ref<Expr> &constraint, std::optional<unsigned> inst);

  ConstraintSet &constraints;
};

} // namespace klee

#endif /* KLEE_CONSTRAINTS_H */