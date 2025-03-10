# Examples

This directory contains potential repositories we are testing Accelerant on. These are organized by repository and issue/commit/PR to make a regression on. 

## [rustc-dev-guide](https://github.com/rust-lang/rustc-dev-guide)


### Potential performance issues
- [Regex caching (diff)](./diffs/rustc-dev-guide/regex_caching.diff)

    Artifically introduce performance issue to recompute regexes per use. 



## [wasmtime](https://github.com/bytecodealliance/wasmtime)

### Potential performance issues
- [PR 9634](https://github.com/bytecodealliance/wasmtime/pull/9634)

    Commit claims to "Optimize memory growth in debug mode which was showing up locally in profiles as being particularly slow."

    Commit: [Commit 27ce0ba](https://github.com/bytecodealliance/wasmtime/commit/27ce0bab2a42a44e1493c77c517faae6685172d9)
- [PR 8303](https://github.com/bytecodealliance/wasmtime/pull/8303)

    Commit claims to optimize fd_read/fd_write

    Associated commit: [Commit 7cc63de](https://github.com/bytecodealliance/wasmtime/commit/7cc63de94dfef4d56051cb8db783660cc4cc773b)
## [regalloc2](https://github.com/bytecodealliance/regalloc2)

### Potential performance issues:
- [Commit 75ccb01](https://github.com/bytecodealliance/regalloc2/commit/75ccb017c102886cb22d8c2d89c4b8227a18eecb)

    Commit claims to resolve performance issues introduced by Rust changes to `sort_unstable_by_key`

## [icu_provider](https://github.com/unicode-org/icu4x/)

### Potential performance issues:
- [PR 287](https://github.com/unicode-org/icu4x/pull/287)

    Commit reports 7% performance increase on some microbenchmarks

    Corresponding commit: [456c03b](https://github.com/unicode-org/icu4x/commit/456c03bfe2bd88bad0bac25830472b1acca01834)
- [PR 4450](https://github.com/unicode-org/icu4x/pull/4450)

    Reports 17% performance increase

    [Commit 4b0000b](https://github.com/unicode-org/icu4x/commit/4b0000b4db629fb1148a3965d7145e9c5846c46f)

## [sval_ref](https://github.com/sval-rs/sval)

### Potential performance issues:
- [PR 158](https://github.com/sval-rs/sval/pull/158)
    Significant reported speedup by using inline
    [Commit 5b8d826](https://github.com/sval-rs/sval/commit/5b8d826a770ac195b6c5721c3617c2c0fbcb960e)