I started a small tool, `placer`, that picks a node for a batch job from our node inventory. The inventory reader and the command line part are done, but two parts are missing, so the crate does not build yet:

1. `impl std::str::FromStr for Quantity` in `src/quantity.rs`, with `type Err = QuantityError`. The accepted text forms, the rounding and the error cases are in the doc comment of `Quantity`.
2. `pub fn place<'a>(nodes: &'a [Node], request: &Request) -> Option<&'a Node>`, available from the crate root as `placer::place`. The placement rules are in the doc comment at the top of `src/lib.rs`.

Please implement both, following the documented rules exactly. Do not change the existing public types, and do not add dependencies (the build has no network). When you are done, `cargo build` and `cargo test` must pass, and `cargo run -- nodes.txt 16 256Gi` must print a node name.
