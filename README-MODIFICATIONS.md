# Record Branch Decisions

Yuxiang: Jameson records the current instruction indicated by `state->pc` every time `Executor::fork()` is called. For reasons I cannot explain, this has the issue that the current instruction PC points to sometimes is past the actual branching instruction itself. Nevertheless, `fork()` is also used outside of branching instructions (e.g. `Call` instruction with function pointer? It is definitely used in one case of `Call`, but I am not sure whether it is function pointer.), so it seems necessary to make a change regardless.

Currently, only `Br` instruction records branch decisions. TODO: `IndirectBr` (low priority, as I think it is only used when `goto` is involved), `Switch`, and `Select` (online sources indicated that this is not guaranteed to be constant-time when compiled into machine code).

`BothBranch`: For each execution path, for each branch along the execution path where either sides could be taken, output the pairs of inputs such that the execution would diverge at this branch.

When visiting a branch for the first time, a message will be sent to `messages.txt`. When finding a counterexample for a branch for the first time, a message will be sent to both the console and `messages.txt`.

# Use Product Program for Branches

## Usage

The function
```cpp
void klee_make_symbolic_sc(void *addr, size_t nbytes, const char *name, int is_secret);
```
works the same way as `klee_make_symbolic()`, with the addition of boolean `is_secret` indicating whether the symblic is a secret.

Test cases for secret-dependent branches are generated as `test#_inst_<instruction_id>_br_<branch_id>.ktest`. Secret-dependent variable values are given as `<variable>` and `<variable>__prime`, with these values leading to diverging branches.

## Implementation

- Secret variables are tracked in the `Array` class
- When adding a constraint in `Executor`, it is added with both the original secret variables and the secret variables replaced with their "prime" counterparts.
- When encountering a branch the current constraint set is augmented by `condition` and `not(condition')`, where `condition'` is `condition` with the secret variables replaced by their "prime" counterparts.

# Generate Comparison with CtChecker

Install Python packages `pandas` and `jinja2`.

Run
```bash
scripts/compare_with_ctchecker.py <ctchecker_result.json> <klee-out-n> <report.html> <plot.png> <name_on_plot_title> --ctchecker-prefix <ctchecker_prefix> --code-path <code_path>
```

- `<ctchecker_prefix>`: For mbedtls, CtChecker is run inside the `library` folder of the the source directory. Therefore, you should set this to `library` so that `bignum.c` is correctly mapped to `library/bignum.c`.
- `<code_path>`: The path to the source directory that you ran KLEE on. The lines of code will be extracted from `<code_path>/<filename>` where `<filename>` is from `visited_branches.json`.