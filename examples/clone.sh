#!/usr/bin/env bash
REPOS=(
    https://github.com/rust-lang/rustc-dev-guide 
    https://github.com/bytecodealliance/wasmtime
)

for repo in "${REPOS[@]}"; do
    repo_dir=$(basename $repo)
    if [ ! -d $repo_dir ]; then
        echo "Cloning $repo to $repo_dir"
        git clone $repo
    else
        echo "Directory $repo_dir already exists"
    fi
done