The Windows build runners do not start since we changed their agent config. The loader rejects this line in the `[cache]` section:

```
dir = "D:\\cache\\"   # windows runners
```

The error is:

```
agentconf: win-runner.conf: line 9: unexpected characters after value: "# windows runners"
```

The file format is described at the top of `src/lib.rs`, and by that description the line is valid. You can reproduce it with `cargo run -- win-runner.conf`.

Please find the cause and fix it in the parser, so that it handles all valid files correctly and not only this line. Keep the public API of the crate as it is. `cargo test` must still pass.
