# Record Branch Decisions

Yuxiang: Jameson records the current instruction indicated by `state->pc` every time `Executor::fork()` is called. For reasons I cannot explain, this has the issue that the current instruction PC points to sometimes is past the actual branching instruction itself. Nevertheless, `fork()` is also used outside of branching instructions (e.g. `Call` instruction with function pointer? It is definitely used in one case of `Call`, but I am not sure whether it is function pointer.), so it seems necessary to make a change regardless.

Currently, only `Br` instruction records branch decisions. TODO: `IndirectBr` (low priority, as I think it is only used when `goto` is involved), `Switch`, and `Select` (online sources indicated that this is not guaranteed to be constant-time when compiled into machine code).

`BothBranch`: For each execution path, for each branch along the execution path where either sides could be taken, output the pairs of inputs such that the execution would diverge at this branch.