`keepr` decides which backup snapshots to keep. The file parsers (`src/input.rs`), the time functions (`src/time.rs`) and the command line are done, but the planner is missing: `plan` and `render` in `src/plan.rs` are `todo!()`.

Implement `plan` and `render` so that they follow the rules R1 to R12 in `docs/RETENTION.md` exactly. Keep the public types and function signatures of the crate as they are, and do not add dependencies (the build has no network).

When you are done, `cargo test` must pass, and this command must print a plan:

```
cargo run -- examples/snapshots.txt examples/policy.txt
```
